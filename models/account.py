# -*- coding: utf-8 -*-
from odoo import api, models, fields
from odoo.tools.translate import _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

class account_move(models.Model):
    _inherit = "account.move"

    @api.depends(
        'dian_document_number',
        'name',
        'document_class_id',
        'document_class_id.doc_code_prefix',
        )
    def _get_document_number(self):
        for r in self:
            if r.dian_document_number and r.document_class_id:
                document_number = (r.document_class_id.doc_code_prefix or '') + r.dian_document_number
            else:
                document_number = r.name
            r.document_number = document_number

    document_class_id = fields.Many2one(
            'dian.document_class',
            string='Document Type',
            copy=False,
            readonly=True,
            states={'draft': [('readonly', False)]},
        )
    dian_document_number = fields.Char(
            string='Document Number',
            copy=False,
            readonly=True,
            states={'draft': [('readonly', False)]},
        )

    canceled = fields.Boolean(
            string="Canceled?",
            readonly=True,
            states={'draft': [('readonly', False)]},
        )
    document_number = fields.Char(
            compute='_get_document_number',
            string='Document Number',
            store=True,
            readonly=True,
            states={'draft': [('readonly', False)]},
        )
    sended = fields.Boolean(
            string="Enviado al DIAN",
            default=False,
            readonly=True,
            states={'draft': [('readonly', False)]},
        )

    def _get_move_imps(self):
        imps = {}
        for l in self.line_ids:
            if l.tax_line_id:
                if l.tax_line_id:
                    if not l.tax_line_id.id in imps:
                        imps[l.tax_line_id.id] = {'tax_id':l.tax_line_id.id, 'credit':0 , 'debit': 0, 'code':l.tax_line_id.dian_code}
                    imps[l.tax_line_id.id]['credit'] += l.credit
                    imps[l.tax_line_id.id]['debit'] += l.debit
                    if l.tax_line_id.activo_fijo:
                        ActivoFijo[1] += l.credit
            elif l.tax_ids and l.tax_ids[0].amount == 0: #caso monto exento
                if not l.tax_ids[0].id in imps:
                    imps[l.tax_ids[0].id] = {'tax_id':l.tax_ids[0].id, 'credit':0 , 'debit': 0, 'code':l.tax_ids[0].dian_code}
                imps[l.tax_ids[0].id]['credit'] += l.credit
                imps[l.tax_ids[0].id]['debit'] += l.debit
        return imps

    def totales_por_movimiento(self):
        move_imps = self._get_move_imps()
        imps = {'iva':0,
                'exento':0,
                'otros_imps':0,
                }
        for key, i in move_imps.items():
            if i['code'] in [14]:
                imps['iva']  += (i['credit'] or i['debit'])
            elif i['code'] == 0:
                imps['exento']  += (i['credit'] or i['debit'])
            else:
                imps['otros_imps']  += (i['credit'] or i['debit'])
        imps['neto'] = self.amount - imps['otros_imps'] - imps['exento'] - imps['iva']
        return imps


class account_move_line(models.Model):
    _inherit = "account.move.line"

    document_class_id = fields.Many2one(
            'dian.document_class',
            string='Document Type',
            related='move_id.document_class_id',
            store=True,
            readonly=True,
        )
    document_number = fields.Char(
            string='Document Number',
            related='move_id.document_number',
            store=True,
            readonly=True,
        )
