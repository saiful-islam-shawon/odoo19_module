from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from .mushak_report import mushak_report_action


class VatRegistrationApplication(models.Model):
    _name = 'vat.registration.application'
    _description = 'Mushak 2.1 VAT / Turnover Tax Registration Application'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(required=True, default=lambda self: _('New'), copy=False, readonly=True)
    version = fields.Integer(default=1, readonly=True)
    previous_application_id = fields.Many2one('vat.registration.application', readonly=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    applicant_type = fields.Selection([
        ('individual', 'Individual'), ('proprietorship', 'Proprietorship'),
        ('partnership', 'Partnership'), ('company', 'Company / RJSC'),
        ('other', 'Other Organisation'),
    ], required=True, default='company', tracking=True)
    registration_type = fields.Selection([
        ('vat', 'VAT Registration'), ('turnover', 'Turnover-tax Enlistment'),
    ], required=True, default='vat', tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'), ('submitted', 'Ready for Filing'), ('approved', 'Approved'), ('rejected', 'Rejected'),
    ], default='draft', required=True, tracking=True)
    legal_name = fields.Char(required=True)
    trade_name = fields.Char()
    tin = fields.Char(string='e-TIN')
    nid_or_passport = fields.Char(string='NID / Passport')
    trade_license_no = fields.Char()
    rjsc_no = fields.Char(string='RJSC Registration No.')
    bida_no = fields.Char(string='BIDA Registration No.')
    registration_date = fields.Date(default=fields.Date.context_today)
    registered_address = fields.Text(required=True)
    contact_address = fields.Text(required=True)
    phone = fields.Char(required=True)
    email = fields.Char()
    vat_circle = fields.Char()
    vat_commissionerate = fields.Char()
    business_nature = fields.Selection([
        ('trading', 'Trading'), ('manufacturing', 'Manufacturing'), ('service', 'Service'), ('mixed', 'Mixed'),
    ], required=True, default='trading')
    business_activity = fields.Text(required=True)
    manufacturing_category = fields.Char()
    service_category = fields.Char()
    business_classification = fields.Char()
    bank_name = fields.Char()
    bank_branch = fields.Char()
    bank_account_no = fields.Char()
    historical_turnover = fields.Monetary(currency_field='currency_id')
    projected_turnover = fields.Monetary(required=True, currency_field='currency_id')
    workforce_count = fields.Integer()
    business_operations = fields.Text()
    branch_unit_ids = fields.Many2many('vat.unit', string='Branches / VAT Units')
    owner_ids = fields.One2many('vat.registration.owner', 'application_id', string='Owners / Directors')
    authorised_person_ids = fields.One2many('vat.registration.authorised.person', 'application_id', string='Authorised Persons')
    document_ids = fields.One2many('vat.registration.document', 'application_id', string='Filing Evidence')
    declaration_name = fields.Char(required=True)
    declaration_date = fields.Date(default=fields.Date.context_today, required=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    approval_date = fields.Date(readonly=True)
    approval_note = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.name == _('New'):
                record.name = self.env['ir.sequence'].next_by_code('zsl_vat.mushak_21') or _('New')
        return records

    @api.constrains('tin', 'phone', 'projected_turnover')
    def _check_identifiers(self):
        for record in self:
            if record.tin and (not record.tin.isdigit() or len(record.tin) < 9 or len(record.tin) > 12):
                raise ValidationError(_('e-TIN must contain 9 to 12 digits.'))
            if record.phone and len(record.phone.replace('+', '').replace('-', '').replace(' ', '')) < 8:
                raise ValidationError(_('Enter a valid contact phone number.'))
            if record.projected_turnover < 0:
                raise ValidationError(_('Projected turnover cannot be negative.'))

    def _check_complete(self):
        for record in self:
            missing = []
            for field, label in [
                ('legal_name', _('legal name')), ('registered_address', _('registered address')),
                ('contact_address', _('contact address')), ('phone', _('contact phone')),
                ('business_activity', _('business activity')), ('declaration_name', _('declarant')),
            ]:
                if not record[field]:
                    missing.append(label)
            if record.applicant_type in ('company', 'partnership') and not record.rjsc_no:
                missing.append(_('RJSC registration number'))
            if record.applicant_type in ('individual', 'proprietorship') and not record.nid_or_passport:
                missing.append(_('NID / passport'))
            if not record.trade_license_no:
                missing.append(_('trade licence number'))
            if not record.authorised_person_ids:
                missing.append(_('at least one authorised person'))
            if not record.document_ids.filtered('attachment_id'):
                missing.append(_('filing evidence attachment'))
            if missing:
                raise UserError(_('Complete Mushak 2.1 before approval: %s.') % ', '.join(missing))

    def action_submit(self):
        self._check_complete()
        self.write({'state': 'submitted'})

    def action_approve(self):
        if not self.env.user.has_group('zsl_vat.group_vat_manager'):
            raise UserError(_('Only a VAT Manager may approve a registration application.'))
        self.filtered(lambda record: record.state == 'submitted').write({
            'state': 'approved', 'approval_date': fields.Date.context_today(self),
            'approval_note': _('Approved by %s') % self.env.user.display_name,
        })

    def action_create_revision(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Only an approved application can be revised.'))
        copy = self.copy({
            'name': _('New'), 'version': self.version + 1, 'previous_application_id': self.id,
            'state': 'draft', 'approval_date': False, 'approval_note': False,
        })
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': copy.id, 'view_mode': 'form'}

    def action_print_application(self):
        return mushak_report_action(self, '2.1')


class VatRegistrationOwner(models.Model):
    _name = 'vat.registration.owner'
    _description = 'Mushak 2.1 Owner / Director'

    application_id = fields.Many2one('vat.registration.application', required=True, ondelete='cascade')
    name = fields.Char(required=True)
    designation = fields.Char()
    nid_or_passport = fields.Char(string='NID / Passport')
    tin = fields.Char(string='e-TIN')
    phone = fields.Char()
    address = fields.Text()


class VatRegistrationAuthorisedPerson(models.Model):
    _name = 'vat.registration.authorised.person'
    _description = 'Mushak 2.1 Authorised Person'

    application_id = fields.Many2one('vat.registration.application', required=True, ondelete='cascade')
    name = fields.Char(required=True)
    designation = fields.Char(required=True)
    nid_or_passport = fields.Char(string='NID / Passport')
    phone = fields.Char(required=True)
    email = fields.Char()
    address = fields.Text()
    authorisation_attachment_id = fields.Many2one('ir.attachment', string='Authorisation Evidence', ondelete='restrict')


class VatRegistrationDocument(models.Model):
    _name = 'vat.registration.document'
    _description = 'Mushak 2.1 Filing Evidence'

    application_id = fields.Many2one('vat.registration.application', required=True, ondelete='cascade')
    document_type = fields.Selection([
        ('trade_license', 'Trade Licence'), ('rjsc', 'RJSC Document'), ('etin', 'e-TIN Certificate'),
        ('bida', 'BIDA Document'), ('bank', 'Bank Evidence'), ('other', 'Other'),
    ], required=True)
    attachment_id = fields.Many2one('ir.attachment', required=True, ondelete='restrict')
    reference = fields.Char()


class VatRegistrationCertificate(models.Model):
    _name = 'vat.registration.certificate'
    _description = 'Mushak 2.3 NBR Registration / Enlistment Certificate'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'effective_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('New'), copy=False, readonly=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    application_id = fields.Many2one('vat.registration.application', ondelete='restrict')
    taxpayer_name = fields.Char(required=True)
    bin = fields.Char(required=True, index=True)
    registration_type = fields.Selection([('vat', 'VAT Registration'), ('turnover', 'Turnover-tax Enlistment')], required=True)
    issue_date = fields.Date(required=True)
    effective_date = fields.Date(required=True)
    issuing_authority = fields.Char(required=True)
    certificate_reference = fields.Char(required=True)
    registered_address = fields.Text(required=True)
    original_pdf_id = fields.Many2one('ir.attachment', string='Original NBR PDF', required=True, ondelete='restrict')
    replaces_id = fields.Many2one('vat.registration.certificate', string='Replaces', ondelete='restrict')
    replaced_by_id = fields.Many2one('vat.registration.certificate', string='Replaced By', readonly=True)
    state = fields.Selection([('active', 'Active'), ('replaced', 'Replaced')], default='active', required=True, readonly=True)
    issuer_id = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)
    bin_mismatch = fields.Boolean(compute='_compute_bin_mismatch', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.user.has_group('zsl_vat.group_vat_manager'):
            raise UserError(_('Only a VAT Manager may upload or replace an NBR certificate.'))
        records = super().create(vals_list)
        for record in records:
            if record.name == _('New'):
                record.name = self.env['ir.sequence'].next_by_code('zsl_vat.mushak_23') or _('New')
            if record.replaces_id:
                record.replaces_id.write({'state': 'replaced', 'replaced_by_id': record.id})
        return records

    @api.depends('bin', 'company_id.vat_bin')
    def _compute_bin_mismatch(self):
        for record in self:
            record.bin_mismatch = bool(record.company_id.vat_bin and record.bin and record.company_id.vat_bin != record.bin)

    def action_print_certificate(self):
        # The original NBR attachment remains the legal certificate.  This is
        # the system-generated prescribed-layout reference copy.
        return mushak_report_action(self, '2.3')
