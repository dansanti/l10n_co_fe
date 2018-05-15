# -*- coding: utf-8 -*-
from odoo import fields, models, api
from odoo.tools.translate import _
from odoo.exceptions import UserError

class dian_document_class(models.Model):
    _name = 'dian.document_class'
    _description = 'DIAN Document Class'

    name = fields.Char(
        'Name', size=120)
    doc_code_prefix = fields.Char(
        'Document Code Prefix', help="Prefix for Documents Codes on Invoices \
        and Account Moves. For eg. 'FAC' will build 'FAC 00001' Document Number")
    code_template = fields.Char(
        'Code Template for Journal')
    dian_code = fields.Integer(
        'DIAN Code', required=True)
    report_name = fields.Char(
        'Name on Reports',
        help='Name that will be printed in reports, for example "CREDIT NOTE"')
    document_type = fields.Selection(
        [
            ('invoice', 'Invoices'),
            ('invoice_in', 'Purchase Invoices'),
            ('debit_note', 'Debit Notes'),
            ('credit_note', 'Credit Notes'),
            ('stock_picking', 'Stock Picking'),
            ('other_document', 'Other Documents')
        ],
        string='Document Type',
        help='It defines some behaviours on automatic journal selection and\
        in menus where it is shown.')
    active = fields.Boolean(
        'Active', default=True)
    dte = fields.Boolean(
        'DTE', required=True)
    use_prefix = fields.Boolean(
            string="Usar Prefix en las referencias DTE",
            default=False,
        )
