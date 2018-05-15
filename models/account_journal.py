# -*- coding: utf-8 -*-
from odoo import api, models, fields
from odoo.tools.translate import _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)


class AccountJournalSiiDocumentClass(models.Model):
    _name = "account.journal.dian_document_class"
    _description = "Journal DIAN Documents"
    _order = 'sequence'

    @api.depends('dian_document_class_id', 'sequence_id')
    def get_secuence_name(self):
        for r in self:
            sequence_name = (': ' + r.sequence_id.name) if r.sequence_id else ''
            name = (r.dian_document_class_id.name or '') + sequence_name
            r.name = name

    name = fields.Char(
            compute="get_secuence_name",
        )
    dian_document_class_id = fields.Many2one(
            'dian.document_class',
            string='Document Type',
            required=True,
        )
    sequence_id = fields.Many2one(
            'ir.sequence',
            string='Entry Sequence',
            help="""This field contains the information related to the numbering \
            of the documents entries of this document type.""",
        )
    journal_id = fields.Many2one(
            'account.journal',
            string='Journal',
            required=True,
        )
    sequence = fields.Integer(
            string='Sequence',
        )

    @api.onchange('dian_document_class_id')
    def check_dian_document_class(self):
        if self.dian_document_class_id and self.sequence_id and self.dian_document_class_id != self.sequence_id.dian_document_class_id:
            raise UserError("El tipo de Documento de la secuencia es distinto")

class account_journal(models.Model):
    _inherit = "account.journal"

    journal_document_class_ids = fields.One2many(
            'account.journal.dian_document_class',
            'journal_id',
            'Documents Class',
        )
    use_documents = fields.Boolean(
            string='Use Documents?',
            default='_get_default_doc',
        )

    restore_mode = fields.Boolean(
            string="Restore Mode",
            default=False,
        )

    @api.onchange('journal_activities_ids')
    def max_actecos(self):
        if len(self.journal_activities_ids) > 4:
            raise UserError("Deben Ser máximo 4 actecos por Diario, seleccione los más significativos para este diario")

    @api.multi
    def _get_default_doc(self):
        self.ensure_one()
        if self.type == 'sale' or self.type == 'purchase':
            self.use_documents = True

    @api.multi
    def name_get(self):
        res = []
        for journal in self:
            currency = journal.currency_id or journal.company_id.currency_id
            name = "%s (%s)" % (journal.name, currency.name)
            if journal.sucursal_id and self.env.context.get('show_full_name', False):
                name = "%s (%s)" % (name, journal.sucursal_id.name)
            res.append((journal.id, name))
        return res
