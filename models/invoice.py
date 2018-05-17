# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError
from datetime import datetime, timedelta, date
from lxml import etree
from lxml.etree import Element, SubElement
from odoo.tools.translate import _

import logging
_logger = logging.getLogger(__name__)

import pytz
from six import string_types
import struct

import collections

try:
    from io import BytesIO
except:
    _logger.warning("no se ha cargado io")
import traceback as tb
import suds.metrics as metrics

try:
    from suds.client import Client
except:
    pass
try:
    import textwrap
except:
    pass

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    import OpenSSL
    from OpenSSL import crypto
    type_ = crypto.FILETYPE_PEM
except:
    _logger.warning('Cannot import OpenSSL library')

try:
    import dicttoxml
except ImportError:
    _logger.warning('Cannot import dicttoxml library')

try:
    import pyqrcode
except ImportError:
    _logger.warning('Cannot import pyqrcode library')

try:
    import base64
except ImportError:
    _logger.warning('Cannot import base64 library')

try:
    import hashlib
except ImportError:
    _logger.warning('Cannot import hashlib library')

try:
    import cchardet
except ImportError:
    _logger.warning('Cannot import cchardet library')

try:
    import xmltodict
except ImportError:
    _logger.warning('Cannot import xmltodict library')

server_url = {
    'CERT':'https://facturaelectronica.dian.gov.co/habilitacion/B2BIntegrationEngine/FacturaElectronica/facturaElectronica.wsdl?',
    'DIAN':'https://facturaelectronica.dian.gov.co/operacion/B2BIntegrationEngine/FacturaElectronica/facturaElectronica.wsdl?',
}

BC = '''-----BEGIN CERTIFICATE-----\n'''
EC = '''\n-----END CERTIFICATE-----\n'''

# hardcodeamos este valor por ahora
import os, sys
USING_PYTHON2 = True if sys.version_info < (3, 0) else False
xsdpath = os.path.dirname(os.path.realpath(__file__)).replace('/models','/static/xsd/')

TYPE2JOURNAL = {
    'out_invoice': 'sale',
    'in_invoice': 'purchase',
    'out_refund': 'sale',
    'in_refund': 'purchase',
}

class Referencias(models.Model):
    _name = 'account.invoice.referencias'

    origen = fields.Char(
            string="Origin",
            )
    dian_referencia_TpoDocRef =  fields.Many2one(
            'dian.document_class',
            string="DIAN Reference Document Type",
        )
    dian_referencia_CodRef = fields.Selection(
            [
                ('1','Anula Documento de Referencia'),
                ('2','Corrige texto Documento Referencia'),
                ('3','Corrige montos')
            ],
            string="DIAN Reference Code",
        )
    motivo = fields.Char(
            string="Motivo",
        )
    invoice_id = fields.Many2one(
            'account.invoice',
            ondelete='cascade',
            index=True,
            copy=False,
            string="Documento",
        )
    fecha_documento = fields.Date(
            string="Fecha Documento",
            required=True,
        )

class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    def _default_journal_document_class_id(self, default=None):
        ids = self._get_available_journal_document_class()
        document_classes = self.env['account.journal.dian_document_class'].browse(ids)
        if default:
            for dc in document_classes:
                if dc.dian_document_class_id.id == default:
                    self.journal_document_class_id = dc.id
        elif document_classes:
            default = self.get_document_class_default(document_classes)
        return default

    def _domain_journal_document_class_id(self):
        domain = self._get_available_journal_document_class()
        return [('id', 'in', domain)]

    def _get_barcode_img(self):
        for r in self:
            texto = '''NumFac: A02F-00117836
FecFac: 20140319105605
NitFac: 808183133
DocAdq: 8081972684
ValFac: 1000.00
ValIva: 160.00
ValOtroIm: 0.00
ValFacIm: 1160.00
CUFE: 2836a15058e90baabbf6bf2e97f05564ea0324a6'''

            qr_code = pyqrcode.create(texto)
            img_as_str = qr_code.png_as_base64_str(scale=5)
            r.dian_barcode_img = img_as_str

    vat_discriminated = fields.Boolean(
            'Discriminate VAT?',
            compute="get_vat_discriminated",
            store=True,
            readonly=False,
            help="Discriminate VAT on Quotations and Sale Orders?",
        )
    journal_document_class_id = fields.Many2one(
            'account.journal.dian_document_class',
            string='Documents Type',
            default=lambda self: self._default_journal_document_class_id(),
            domain=_domain_journal_document_class_id,
            readonly=True,
            store=True,
            states={'draft': [('readonly', False)]},
        )
    dian_document_class_id = fields.Many2one(
            'dian.document_class',
            related='journal_document_class_id.dian_document_class_id',
            string='Document Type',
            copy=False,
            readonly=True,
            store=True,
        )
    dian_document_number = fields.Char(
            string='Document Number',
            copy=False,
            readonly=True,
        )
    document_number = fields.Char(
            compute='_get_document_number',
            string='Document Number',
            readonly=True,
        )
    next_invoice_number = fields.Integer(
            related='journal_document_class_id.sequence_id.number_next_actual',
            string='Next Document Number',
            readonly=True,
        )
    use_documents = fields.Boolean(
            related='journal_id.use_documents',
            string='Use Documents?',
            readonly=True,
        )
    referencias = fields.One2many(
            'account.invoice.referencias',
            'invoice_id',
            readonly=True,
            states={'draft': [('readonly', False)]},
    )
    forma_pago = fields.Selection(
            [
                    ('1','Contado'),
                    ('2','Crédito'),
                    ('3','Gratuito')
            ]
            ,string="Forma de pago",
            readonly=True,
            states={'draft': [('readonly', False)]},
            default='1',
        )
    contact_id = fields.Many2one(
            'res.partner',
            string="Contacto",
        )
    dian_batch_number = fields.Integer(
            copy=False,
            string='Batch Number',
            readonly=True,
            help='Batch number for processing multiple invoices together',
        )
    dian_barcode = fields.Char(
            copy=False,
            string=_('DIAN Barcode'),
            help='DIAN Barcode Name',
            readonly=True,
            states={'draft': [('readonly', False)]},
        )
    dian_barcode_img = fields.Binary(
            string=_('DIAN Barcode Image'),
            help='DIAN Barcode Image in QR format',
            compute="_get_barcode_img",
        )
    dian_message = fields.Text(
            string='DIAN Message',
            copy=False,
        )
    dian_xml_dte = fields.Text(
            string='DIAN XML DTE',
            copy=False,
            readonly=True,
            states={'draft': [('readonly', False)]},
        )
    dian_xml_request = fields.Many2one(
            'dian.xml.envio',
            string='DIAN XML Request',
            copy=False,
        )
    dian_result = fields.Selection(
            [
                ('draft', 'Borrador'),
                ('NoEnviado', 'No Enviado'),
                ('EnCola','En cola de envío'),
                ('Enviado', 'Enviado'),
                ('Aceptado', 'Aceptado'),
                ('Rechazado', 'Rechazado'),
                ('Reparo', 'Reparo'),
                ('Proceso', 'Procesado'),
                ('Anulado', 'Anulado'),
            ],
            string='Resultado',
            help="DIAN request result",
        )
    canceled = fields.Boolean(
            string="Canceled?",
            copy=False,
        )
    purchase_to_done = fields.Many2many(
            'purchase.order',
            string="Ordenes de Compra a validar",
            domain=[('state', 'not in',['done', 'cancel'] )],
            readonly=True,
            states={'draft': [('readonly', False)]},
    )

    @api.model
    def _prepare_refund(self, invoice, date_invoice=None, date=None, description=None, journal_id=None, tipo_nota=61, mode='1'):
        values = super(AccountInvoice, self)._prepare_refund(invoice, date_invoice, date, description, journal_id)
        document_type = self.env['account.journal.dian_document_class'].search(
                [
                    ('dian_document_class_id.dian_code','=', tipo_nota),
                    ('journal_id','=', invoice.journal_id.id),
                ],
                limit=1,
            )
        if invoice.type == 'out_invoice':
            type = 'out_refund'
        elif invoice.type == 'out_refund':
            type = 'out_invoice'
        elif invoice.type == 'in_invoice':
            type = 'in_refund'
        elif invoice.type == 'in_refund':
            type = 'in_invoice'
        values.update({
                'type': type,
                'journal_document_class_id': document_type.id,
                'turn_issuer': invoice.turn_issuer.id,
                'referencias':[[0,0, {
                        'origen': int(invoice.dian_document_number or invoice.reference),
                        'dian_referencia_TpoDocRef': invoice.dian_document_class_id.id,
                        'dian_referencia_CodRef': mode,
                        'motivo': description,
                        'fecha_documento': invoice.date_invoice
                    }]],
            })
        return values

    @api.multi
    @api.returns('self')
    def refund(self, date_invoice=None, date=None, description=None, journal_id=None, tipo_nota=61, mode='1'):
        new_invoices = self.browse()
        for invoice in self:
            # create the new invoice
            values = self._prepare_refund(invoice, date_invoice=date_invoice, date=date,
                                    description=description, journal_id=journal_id,
                                    tipo_nota=tipo_nota, mode=mode)
            refund_invoice = self.create(values)
            invoice_type = {'out_invoice': ('customer invoices credit note'),
                            'out_refund': ('customer invoices debit note'),
                            'in_invoice': ('vendor bill credit note'),
                            'in_refund': ('vendor bill debit note')}
            message = _("This %s has been created from: <a href=# data-oe-model=account.invoice data-oe-id=%d>%s</a>") % (invoice_type[invoice.type], invoice.id, invoice.number)
            refund_invoice.message_post(body=message)
            new_invoices += refund_invoice
        return new_invoices

    def get_document_class_default(self, document_classes):
        document_class_id = None
        #if self.turn_issuer.vat_affected not in ['SI', 'ND']:
        #    exempt_ids = [
        #        self.env.ref('l10n_co_fe.dc_y_f_dtn').id,
        #        self.env.ref('l10n_co_fe.dc_y_f_dte').id]
        #    for document_class in document_classes:
        #        if document_class.dian_document_class_id.id in exempt_ids:
        #            document_class_id = document_class.id
        #            break
        #        else:
        #            document_class_id = document_classes.ids[0]
        #else:
        document_class_id = document_classes.ids[0]
        return document_class_id

#    @api.onchange('journal_id', 'company_id')
    def _set_available_issuer_turns(self):
        for rec in self:
            if rec.company_id:
                available_turn_ids = rec.company_id.company_activities_ids
                for turn in available_turn_ids:
                    rec.turn_issuer= turn.id

    @api.multi
    def name_get(self):
        TYPES = {
            'out_invoice': _('Invoice'),
            'in_invoice': _('Supplier Invoice'),
            'out_refund': _('Refund'),
            'in_refund': _('Supplier Refund'),
        }
        result = []
        for inv in self:
            result.append(
                (inv.id, "%s %s" % (inv.document_number or TYPES[inv.type], inv.name or '')))
        return result

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        recs = self.browse()
        if name:
            recs = self.search(
                [('document_number', '=', name)] + args, limit=limit)
        if not recs:
            recs = self.search([('name', operator, name)] + args, limit=limit)
        return recs.name_get()

#    @api.onchange('partner_id')
    def update_journal(self):
        self.journal_id = self._default_journal()
        self.set_default_journal()
        return self.update_domain_journal()

#    @api.onchange('company_id')
    def _refreshRecords(self):
        self.journal_id = self._default_journal()
        journal = self.journal_id
        for line in self.invoice_line_ids:
            tax_ids = []
            if self._context.get('type') in ('out_invoice', 'in_refund'):
                line.account_id = journal.default_credit_account_id.id
            else:
                line.account_id = journal.default_debit_account_id.id
            if self._context.get('type') in ('out_invoice', 'out_refund'):
                for tax in line.product_id.taxes_id:
                    if tax.company_id.id == self.company_id.id:
                        tax_ids.append(tax.id)
                    else:
                        tax_n = self._buscarTaxEquivalente(tax)
                        if not tax_n:
                            tax_n = self._crearTaxEquivalente(tax)
                        tax_ids.append(tax_n.id)
                line.product_id.taxes_id = False
                line.product_id.taxes_id = tax_ids
            else:
                for tax in line.product_id.supplier_taxes_id:
                    if tax.company_id.id == self.company_id.id:
                        tax_ids.append(tax.id)
                    else:
                        tax_n = self._buscarTaxEquivalente(tax)
                        if not tax_n:
                            tax_n = self._crearTaxEquivalente(tax)
                        tax_ids.append(tax_n.id)
                line.invoice_line_tax_ids = False
                line.product_id.supplier_taxes_id.append = tax_ids
            line.invoice_line_tax_ids = False
            line.invoice_line_tax_ids = tax_ids

    def _get_available_journal_document_class(self):
        context = dict(self._context or {})
        journal_id = self.journal_id
        if not journal_id and 'default_journal_id' in context:
            journal_id = self.env['account.journal'].browse(context['default_journal_id'])
        if not journal_id:
            journal_id = self.env['account.journal'].search([('type','=','sale')],limit=1)
        invoice_type = self.type or context.get('default_type', False)
        if not invoice_type:
            invoice_type = 'in_invoice' if journal_id.type == 'purchase' else 'out_invoice'
        document_class_ids = []
        nd = False
        for ref in self.referencias:
            if not nd:
                nd = ref.dian_referencia_CodRef
        if invoice_type in ['out_invoice', 'in_invoice', 'out_refund', 'in_refund']:
            if journal_id:
                domain = [
                    ('journal_id', '=', journal_id.id),
                 ]
            else:
                operation_type = self.get_operation_type(invoice_type)
                domain = [
                    ('journal_id.type', '=', operation_type),
                 ]
            if invoice_type  in [ 'in_refund', 'out_refund']:
                domain += [('dian_document_class_id.document_type','in',['credit_note'] )]
            else:
                options = ['invoice', 'invoice_in']
                if nd:
                    options.append('debit_note')
                domain += [('dian_document_class_id.document_type','in', options )]
            document_classes = self.env[
                'account.journal.dian_document_class'].search(domain)
            document_class_ids = document_classes.ids
        return document_class_ids

#    @api.onchange('journal_id', 'partner_id')
    def update_domain_journal(self):
        document_classes = self._get_available_journal_document_class()
        result = {'domain':{
            'journal_document_class_id' : [('id', 'in', document_classes)],
        }}
        return result

    @api.depends('journal_id')
    @api.onchange('journal_id', 'partner_id')
    def set_default_journal(self, default=None):
        if not self.journal_document_class_id or self.journal_document_class_id.journal_id != self.journal_id:
            query = []
            if not default and not self.journal_document_class_id:
                query.append(
                    ('dian_document_class_id','=', self.journal_document_class_id.dian_document_class_id.id),
                )
            if self.journal_document_class_id.journal_id != self.journal_id or not default:
                query.append(
                    ('journal_id', '=', self.journal_id.id)
                )
            if query:
                default = self.env['account.journal.dian_document_class'].search(
                    query,
                    order='sequence asc',
                    limit=1,
                ).id
            self.journal_document_class_id = self._default_journal_document_class_id(default)

#    @api.depends('dian_document_number', 'number')
    def _get_document_number(self):
        for inv in self:
            if inv.dian_document_number and inv.dian_document_class_id:
                document_number = (
                    inv.dian_document_class_id.doc_code_prefix or '') + inv.dian_document_number
            else:
                document_number = inv.number
            inv.document_number = document_number

#    @api.one
#    @api.constrains('reference', 'partner_id', 'company_id', 'type','journal_document_class_id')
    def _check_reference_in_invoice(self):
        if self.type in ['in_invoice', 'in_refund'] and self.reference:
            domain = [('type', '=', self.type),
                      ('reference', '=', self.reference),
                      ('partner_id', '=', self.partner_id.id),
                      ('journal_document_class_id.dian_document_class_id', '=',
                       self.journal_document_class_id.dian_document_class_id.id),
                      ('company_id', '=', self.company_id.id),
                      ('id', '!=', self.id)]
            invoice_ids = self.search(domain)
            if invoice_ids:
                raise UserError(u'El numero de factura debe ser unico por Proveedor.\n'\
                                u'Ya existe otro documento con el numero: %s para el proveedor: %s' %
                                (self.reference, self.partner_id.display_name))

    @api.multi
    def action_move_create(self):
        for obj_inv in self:
            invtype = obj_inv.type
            if obj_inv.journal_document_class_id and not obj_inv.dian_document_number:
                if invtype in ('out_invoice', 'out_refund'):
                    if not obj_inv.journal_document_class_id.sequence_id:
                        raise UserError(_(
                            'Please define sequence on the journal related documents to this invoice.'))
                    dian_document_number = obj_inv.journal_document_class_id.sequence_id.next_by_id()
                    prefix = obj_inv.journal_document_class_id.dian_document_class_id.doc_code_prefix or ''
                    move_name = (prefix + str(dian_document_number)).replace(' ','')
                    obj_inv.write({'move_name': move_name})
                elif invtype in ('in_invoice', 'in_refund'):
                    dian_document_number = obj_inv.reference
        super(AccountInvoice, self).action_move_create()
        for obj_inv in self:
            invtype = obj_inv.type
            if obj_inv.journal_document_class_id and not obj_inv.dian_document_number:
                obj_inv.write({'dian_document_number': dian_document_number})
            document_class_id = obj_inv.dian_document_class_id.id
            guardar = {'document_class_id': document_class_id,
                'dian_document_number': obj_inv.dian_document_number,
                'no_rec_code':obj_inv.no_rec_code,
                'iva_uso_comun':obj_inv.iva_uso_comun,}
            obj_inv.move_id.write(guardar)
        return True

    def get_operation_type(self, invoice_type):
        if invoice_type in ['in_invoice', 'in_refund']:
            operation_type = 'purchase'
        elif invoice_type in ['out_invoice', 'out_refund']:
            operation_type = 'sale'
        else:
            operation_type = False
        return operation_type

    @api.multi
    def _check_duplicate_supplier_reference(self):
        for invoice in self:
            if invoice.type in ('in_invoice', 'in_refund') and invoice.reference:
                if self.search(
                    [
                        ('reference','=', invoice.reference),
                        ('journal_document_class_id','=',invoice.journal_document_class_id.id),
                        ('partner_id','=', invoice.partner_id.id),
                        ('type', '=', invoice.type),
                        ('id', '!=', invoice.id),
                     ]):
                    raise UserError('El documento %s, Folio %s de la Empresa %s ya se en cuentra registrado' % ( invoice.journal_document_class_id.dian_document_class_id.name, invoice.reference, invoice.partner_id.name))

    @api.multi
    def invoice_validate(self):
        for inv in self:
            if not inv.journal_id.use_documents or not inv.dian_document_class_id.dte:
                continue
            inv.dian_result = 'NoEnviado'
            inv.responsable_envio = self.env.user.id
            if inv.type in ['out_invoice', 'out_refund']:
                if inv.journal_id.restore_mode:
                    inv.dian_result = 'Proceso'
                else:
                    inv._timbrar()
                    if inv._es_boleta() and not inv._nc_boleta():
                        inv.dian_result = 'Proceso'
                        continue
                    tiempo_pasivo = (datetime.now() + timedelta(hours=int(self.env['ir.config_parameter'].sudo().get_param('account.auto_send_dte', default=12))))
                    self.env['dian.cola_envio'].create({
                                                'doc_ids':[inv.id],
                                                'model':'account.invoice',
                                                'user_id':self.env.user.id,
                                                'tipo_trabajo': 'pasivo',
                                                'date_time': tiempo_pasivo,
                                                'send_email': False if inv.company_id.dte_service_provider=='CERT' or self.env['ir.config_parameter'].sudo().get_param('account.auto_send_email', default=True) else True,
                                                })
            if inv.purchase_to_done:
                for ptd in inv.purchase_to_done:
                    ptd.write({'state': 'done'})
        return super(AccountInvoice, self).invoice_validate()

    @api.model
    def create(self, vals):
        inv = super(AccountInvoice, self).create(vals)
        inv.update_domain_journal()
        inv.set_default_journal()
        return inv

    @api.model
    def _default_journal(self):
        if self._context.get('default_journal_id', False):
            return self.env['account.journal'].browse(self._context.get('default_journal_id'))
        company_id = self._context.get('company_id', self.company_id or self.env.user.company_id)
        if self._context.get('honorarios', False):
            inv_type = self._context.get('type', 'out_invoice')
            inv_types = inv_type if isinstance(inv_type, list) else [inv_type]
            domain = [
                ('journal_document_class_ids.dian_document_class_id.document_letter_id.name','=','M'),
                ('type', 'in', [TYPE2JOURNAL[ty] for ty in inv_types if ty in TYPE2JOURNAL])
                ('company_id', '=', company_id.id),
            ]
            journal_id = self.env['account.journal'].search(domain, limit=1)
            return journal_id
        inv_type = self._context.get('type', 'out_invoice')
        inv_types = inv_type if isinstance(inv_type, list) else [inv_type]
        domain = [
            ('type', 'in', [TYPE2JOURNAL[ty] for ty in inv_types if ty in TYPE2JOURNAL]),
            ('company_id', '=', company_id.id),
        ]
        return self.env['account.journal'].search(domain, limit=1, order="sequence asc")

    def time_stamp(self, formato='%Y-%m-%dT%H:%M:%S'):
        tz = pytz.timezone('America/Santiago')
        return datetime.now(tz).strftime(formato)

    def _get_xsd_file(self, validacion, path=False):
        validacion_type = self._get_xsd_types()
        return (path or xsdpath) + validacion_type[validacion]

    def xml_validator(self, some_xml_string, validacion='doc'):
        if validacion == 'bol':
            return True
        xsd_file = self._get_xsd_file(validacion)
        try:
            xmlschema_doc = etree.parse(xsd_file)
            xmlschema = etree.XMLSchema(xmlschema_doc)
            xml_doc = etree.fromstring(some_xml_string)
            result = xmlschema.validate(xml_doc)
            if not result:
                xmlschema.assert_(xml_doc)
            return result
        except AssertionError as e:
            _logger.warning(etree.tostring(xml_doc))
            raise UserError(_('XML Malformed Error:  %s') % e.args)


    def _cabezera(self, xml_timbrado):
        return '''<fe:Invoice xmlns:fe="http://www.dian.gov.co/contratos/facturaelectronica/v1" xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:clm54217="urn:un:unece:uncefact:codelist:specification:54217:2001" xmlns:clm66411="urn:un:unece:uncefact:codelist:specification:66411:2001" xmlns:clmIANAMIMEMediaType="urn:un:unece:uncefact:codelist:specification:IANAMIMEMediaType:2003" xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" xmlns:qdt="urn:oasis:names:specification:ubl:schema:xsd:QualifiedDatatypes-2" xmlns:sts="http://www.dian.gov.co/contratos/facturaelectronica/v1/Structures" xmlns:udt="urn:un:unece:uncefact:data:specification:UnqualifiedDataTypesSchemaModule:2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.dian.gov.co/contratos/facturaelectronica/v1 ../xsd/DIAN_UBL.xsd urn:un:unece:uncefact:data:specification:UnqualifiedDataTypesSchemaModule:2 ../../ubl2/common/UnqualifiedDataTypeSchemaModule-2.0.xsd urn:oasis:names:specification:ubl:schema:xsd:QualifiedDatatypes-2 ../../ubl2/common/UBL-QualifiedDatatypes-2.0.xsd">%s</fe:Invoice>''' %xml_timbrado

    def ensure_str(self,x, encoding="utf-8", none_ok=False):
        if none_ok is True and x is None:
            return x
        if not isinstance(x, str):
            x = x.decode(encoding)
        return x

    def long_to_bytes(self, n, blocksize=0):
        s = b''
        if USING_PYTHON2:
            n = long(n)  # noqa
        pack = struct.pack
        while n > 0:
            s = pack(b'>I', n & 0xffffffff) + s
            n = n >> 32
        # strip off leading zeros
        for i in range(len(s)):
            if s[i] != b'\000'[0]:
                break
        else:
            # only happens when n == 0
            s = b'\000'
            i = 0
        s = s[i:]
        # add back some pad bytes.  this could be done more efficiently w.r.t. the
        # de-padding being done above, but sigh...
        if blocksize > 0 and len(s) % blocksize:
            s = (blocksize - len(s) % blocksize) * b'\000' + s
        return s

    def sign_full_xml(self, message, privkey, cert, uri, type='doc'):
        doc = etree.fromstring(message)
        string = etree.tostring(doc[0])
        mess = etree.tostring(etree.fromstring(string), method="c14n")
        digest = base64.b64encode(self.digest(mess))
        reference_uri='#'+uri
        signed_info = Element("SignedInfo")
        c14n_method = SubElement(signed_info, "CanonicalizationMethod", Algorithm='http://www.w3.org/TR/2001/REC-xml-c14n-20010315')
        sign_method = SubElement(signed_info, "SignatureMethod", Algorithm='http://www.w3.org/2000/09/xmldsig#rsa-sha1')
        reference = SubElement(signed_info, "Reference", URI=reference_uri)
        transforms = SubElement(reference, "Transforms")
        SubElement(transforms, "Transform", Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
        digest_method = SubElement(reference, "DigestMethod", Algorithm="http://www.w3.org/2000/09/xmldsig#sha1")
        digest_value = SubElement(reference, "DigestValue")
        digest_value.text = digest
        signed_info_c14n = etree.tostring(signed_info,method="c14n",exclusive=False,with_comments=False,inclusive_ns_prefixes=None)
        if type in ['doc','recep']:
            att = 'xmlns="http://www.w3.org/2000/09/xmldsig#"'
        else:
            att = 'xmlns="http://www.w3.org/2000/09/xmldsig#" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        #@TODO Find better way to add xmlns:xsi attrib
        signed_info_c14n = signed_info_c14n.decode().replace("<SignedInfo>", "<SignedInfo %s>" % att )
        sig_root = Element("Signature",attrib={'xmlns':'http://www.w3.org/2000/09/xmldsig#'})
        sig_root.append(etree.fromstring(signed_info_c14n))
        signature_value = SubElement(sig_root, "SignatureValue")
        key = crypto.load_privatekey(type_,privkey.encode('ascii'))
        signature = crypto.sign(key,signed_info_c14n,'sha1')
        signature_value.text = textwrap.fill(base64.b64encode(signature).decode(),64)
        key_info = SubElement(sig_root, "KeyInfo")
        key_value = SubElement(key_info, "KeyValue")
        rsa_key_value = SubElement(key_value, "RSAKeyValue")
        modulus = SubElement(rsa_key_value, "Modulus")
        key = load_pem_private_key(privkey.encode('ascii'), password=None, backend=default_backend())
        modulus.text =  textwrap.fill(base64.b64encode(self.long_to_bytes(key.public_key().public_numbers().n)).decode(),64)
        exponent = SubElement(rsa_key_value, "Exponent")
        exponent.text = self.ensure_str(base64.b64encode(self.long_to_bytes(key.public_key().public_numbers().e)))
        x509_data = SubElement(key_info, "X509Data")
        x509_certificate = SubElement(x509_data, "X509Certificate")
        x509_certificate.text = '\n'+textwrap.fill(cert,64)
        msg = etree.tostring(sig_root)
        msg = msg if self.xml_validator(msg, 'sig') else ''
        fulldoc = self._append_sig(type, msg, message)
        return fulldoc if self.xml_validator(fulldoc, type) else ''

    def get_folio(self):
        # saca el folio directamente de la secuencia
        return int(self.dian_document_number)

    def format_vat(self, value, con_cero=False):
        ''' Se Elimina el 0 para prevenir problemas con el dian, ya que las muestras no las toma si va con
        el 0 , y tambien internamente se generan problemas, se mantiene el 0 delante, para cosultas, o sino retorna "error de datos"'''
        if not value or value=='' or value == 0:
            value ="CL666666666"
            #@TODO opción de crear código de cliente en vez de rut genérico
        rut = value[:10] + '-' + value[10:]
        if not con_cero:
            rut = rut.replace('CL0','')
        rut = rut.replace('CL','')
        return rut

    def digest(self, data):
        sha1 = hashlib.new('sha1', data)
        return sha1.digest()

    def signmessage(self, texto, key):
        key = crypto.load_privatekey(type_, key)
        signature = crypto.sign(key, texto, 'sha1')
        text = base64.b64encode(signature).decode()
        return textwrap.fill( text, 64)

    def _acortar_str(self, texto, size=1):
        c = 0
        cadena = ""
        while c < size and c < len(texto):
            cadena += texto[c]
            c += 1
        return cadena

    @api.multi
    def do_dte_send_invoice(self, n_atencion=None):
        ids = []
        for inv in self.with_context(lang='es_CL'):
            if inv.dian_result in ['','NoEnviado','Rechazado'] and not inv._es_boleta() and not inv._nc_boleta():
                if inv.dian_result in ['Rechazado']:
                    inv._timbrar()
                inv.dian_result = 'EnCola'
                ids.append(inv.id)
        if not isinstance(n_atencion, string_types):
            n_atencion = ''
        if ids:
            self.env['dian.cola_envio'].create({
                                    'doc_ids': ids,
                                    'model':'account.invoice',
                                    'user_id':self.env.user.id,
                                    'tipo_trabajo': 'envio',
                                    'n_atencion': n_atencion,
                                    'send_email': False if self[0].company_id.dte_service_provider=='CERT' or self.env['ir.config_parameter'].sudo().get_param('account.auto_send_email', default=True) else True,
                                    })

    def _ssc(self):
        return hashlib.new('sha384', str(self.company_id.software_id) + str(self.company_id.software_pin))

    def _rangos(self, rangos):
        rango = self.journal_document_class_id.sequence_id.get_rango()
        exten = SubElement(rangos, 'ext:UBLExtension')
        content = SubElement(exten,  'ext:ExtensionContent')
        dianExt = SubElement(content , 'sts:DianExtensions')
        ic = SubElement(dianExt , 'sts:InvoiceControl')
        SubElement(ic , 'sts:InvoiceAuthorization').text = rango.code
        auth = SubElement(ic , 'sts:AuthorizationPeriod')
        SubElement(auth , 'cbc:StartDate').text = rango.start_date
        SubElement(auth , 'cbc:EndDate').text = rango.end_date
        auth_inv = SubElement(ic , 'sts:AuthorizedInvoices')
        SubElement(auth_inv , 'sts:Prefix').text = rango.prefix
        SubElement(auth_inv , 'sts:From').text = rango.start_nm
        SubElement(auth_inv , 'sts:To').text = rango.final_nm
        inv_sec = SubElement(dianExt , 'sts:InvoiceSource')
        SubElement(inv_sec , 'cbc:IdentificationCode', attrib={"listAgencyID":"6", "listAgencyName":"United Nations Economic Commission for Europe", "listSchemeURI":"urn:oasis:names:specification:ubl:codelist:gc:CountryIdentificationCode-2.0"}).text = "CO"
        sp = SubElement(dianExt , 'sts:SoftwareProvider')
        SubElement(sp , 'sts:ProviderID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Direccion de Impuestos y Aduanas Nacionales)"').text = self.company_id.provider_id
        SubElement(sp , 'sts:SoftwareID', attrib={ "schemeAgencyID":"195", "schemeAgencyName":"CO, DIAN (Direccion de Impuestos y Aduanas Nacionales)"}).text = self.company_id.software_id
        SubElement(dianExt , 'sts:SoftwareSecurityCode', attrib={"schemeAgencyID":"195", "schemeAgencyName":"CO, DIAN (Direccion de Impuestos y Aduanas Nacionales)"}).text = self._ssc()

    def _firma(self, firma):
        exten = SubElement(firma, 'ext:UBLExtension')
        content = SubElement(exten,  'ext:ExtensionContent')
        sig_root = SubElement(content, 'ds:Signature', attrib={"xmlns:ds":"http://www.w3.org/2000/09/xmldsig#", "Id":"xmldsig-88fbfc45-3be2-4c4a-83ac-0796e1bad4c5"})
        sig_info = SubElement(sig_root, 'ds:SignedInfo')
        SubElement(sig_info, 'ds:CanonicalizationMethod', Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
        SubElement(sig_info, 'ds:SignatureMethod', Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1")
        ref = SubElement(sig_info, 'ds:Reference', attrib={ "Id":"xmldsig-88fbfc45-3be2-4c4a-83ac-0796e1bad4c5-ref0", "URI":""})
        trans = SubElement(ref, 'ds:Transforms')
        SubElement(trans, 'ds:Transform', Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature")
        SubElement(ref, 'ds:DigestMethod', Algorithm="http://www.w3.org/2000/09/xmldsig#sha1")
        SubElement(ref, 'ds:DigestValue').text = "6F5KPfMMBWPbl8ImvaG9z9NFSLE="
        ref = SubElement(sig_info, 'ds:Reference', attrib={ "URI":"#xmldsig-87d128b5-aa31-4f0b-8e45-3d9cfa0eec26-keyinfo"})
        SubElement(ref, 'ds:DigestMethod', Algorithm="http://www.w3.org/2000/09/xmldsig#sha1")
        SubElement(ref, 'ds:DigestValue').text = "0iE/FGZgLfbnV9DhUaDBBVPjn44="
        ref = SubElement(sig_info, 'ds:Reference', attrib={"Type":"http://uri.etsi.org/01903#SignedProperties", "URI":"#xmldsig-88fbfc45-3be2-4c4a-83ac-0796e1bad4c5-signedprops"})
        SubElement(ref, 'ds:DigestMethod', Algorithm="http://www.w3.org/2000/09/xmldsig#sha1")
        SubElement(ref, 'ds:DigestValue').text = "mnp1FDOGYZ97yw3pTeldFRVg+64="

        sigt.append(etree.fromstring(signed_info_c14n))
        signature_value = SubElement(sig_root, "ds:SignatureValue", attrib={"ID": "xmldsig-88fbfc45-3be2-4c4a-83ac-0796e1bad4c5-sigvalue"})
        key = crypto.load_privatekey(type_,privkey.encode('ascii'))
        signature = crypto.sign(key,signed_info_c14n,'sha1')
        signature_value.text = textwrap.fill(base64.b64encode(signature).decode(),64)
        key_info = SubElement(sig_root, "ds:KeyInfo", attrib={"ID": "xmldsig-87d128b5-aa31-4f0b-8e45-3d9cfa0eec26-keyinfo"})
        x509_data = SubElement(key_info, "ds:X509Data")
        x509_certificate = SubElement(x509_data, "ds:X509Certificate")
        x509_certificate.text = '\n'+textwrap.fill(cert,64)


        obj = SubElement(sig_root, 'ds:Object')
        qp = SubElement(obj, 'xades:QualifyingProperties', attrib={"xmlns:xades":"http://uri.etsi.org/01903/v1.3.2#", "xmlns:xades141":"http://uri.etsi.org/01903/v1.4.1#", "Target":"#xmldsig-88fbfc45-3be2-4c4a-83ac-0796e1bad4c5"})
        sp = SubElement(qp, 'xades:SignedProperties', attrib={"Id":"xmldsig-88fbfc45-3be2-4c4a-83ac-0796e1bad4c5-signedprops"})
        ssp = SubElement(sp, 'xades:SignedSignatureProperties')
        SubElement(ssp, 'xades:SigningTime').text = "2016-07-12T11:17:38.639-05:00"
        sc = SubElement(ssp, 'xades:SigningCertificate')
        cert = SubElement(sc, 'xades:Cert')
        certd = SubElement(cert, 'xades:CertDigest')
        SubElement(certd, 'ds:DigestMethod', Algorithm="http://www.w3.org/2000/09/xmldsig#sha1")
        SubElement(certd, 'ds:DigestValue').text = "2el6MfWvYsvEaa/TV513a7tVK0g="
        iss = SubElement(cert, 'xades:IssuerSerial')
        SubElement(iss, 'ds:X509IssuerName').text = "C=CO,L=Bogota D.C.,O=Andes SCD.,OU=Division de certificacion entidad final,CN=CA ANDES SCD S.A. Clase II,1.2.840.113549.1.9.1=#1614696e666f40616e6465737363642e636f6d2e636f"
        SubElement(iss, 'ds:X509SerialNumber').text = "9128602840918470673"
        cert = SubElement(sc, 'xades:Cert')
        certd = SubElement(cert, 'xades:CertDigest')
        SubElement(certd, 'ds:DigestMethod', Algorithm="http://www.w3.org/2000/09/xmldsig#sha1")
        SubElement(certd,'ds:DigestValue').text = "YGJTXnOzmebG2Mc6A/QapNi1PRA="
        iss = SubElement(cert, 'xades:IssuerSerial')
        SubElement(iss, 'ds:X509IssuerName').text = "C=CO,L=Bogota D.C.,O=Andes SCD,OU=Division de certificacion,CN=ROOT CA ANDES SCD S.A.,1.2.840.113549.1.9.1=#1614696e666f40616e6465737363642e636f6d2e636f"
        SubElement(iss, 'ds:X509SerialNumber').text = "7958418607150926283"
        cert = SubElement(sc, 'xades:Cert')
        certd = SubElement(cert, 'xades:CertDigest')
        SubElement(certd, 'ds:DigestMethod', Algorithm="http://www.w3.org/2000/09/xmldsig#sha1")
        SubElement(certd, 'ds:DigestValue').text = "6EVr7OINyc49AgvNkie19xul55c="
        iss = SubElement(cert, 'xades:IssuerSerial')
        SubElement(iss, 'ds:X509IssuerName').text = "C=CO,L=Bogota D.C.,O=Andes SCD,OU=Division de certificacion,CN=ROOT CA ANDES SCD S.A.,1.2.840.113549.1.9.1=#1614696e666f40616e6465737363642e636f6d2e636f"
        SubElement(iss, 'ds:X509SerialNumber').text = "3248112716520923666"
        spi = SubElement(ssp, 'xades:SignaturePolicyIdentifier')
        spid = SubElement(spi, 'xades:SignaturePolicyId')
        sig_id = SubElement(spid, 'xades:SigPolicyId')
        SubElement(sig_id, 'xades:Identifier').text = "https://facturaelectronica.dian.gov.co/politicadefirma/v1/politicadefirmav1.pdf"
        sph = SubElement(spid, 'xades:SigPolicyHash')
        sphm = SubElement(sph, 'ds:DigestMethod', Algorithm="http://www.w3.org/2000/09/xmldsig#sha1")
        SubElement(sphm, 'ds:DigestValue').text = "61fInBICBQOCBwuTwlaOZSi9HKc="
        sr = SubElement(ssp, 'xades:SignerRole')
        cr = SubElement(sr, 'xades:ClaimedRoles')
        SubElement(cr, 'xades:ClaimedRole').text = "supplier"

    def _note(self):
        return '''Set de pruebas =  f-s0001_900373115_0d2e2_R9000000500017960-PRUE-A_cufePRUE980007161_0L_900373115  2016-07-12 politica de firma DIAN&#13;
NumFac: PRUE980007161&#13;
FecFac: 20160712003140&#13;
ValFac: 1134840.69&#13;
CodImp1: 01&#13;
ValImp1: 0.00&#13;
CodImp2: 02&#13;
ValImp2: 46982.40&#13;
CodImp3: 03&#13;
ValImp3: 109625.61&#13;
ValImp: 1291448.7&#13;
NitOFE: 900373115&#13;
TipAdq: 22&#13;
NumAdq: 11333000&#13;
String: PRUE980007161201607120031401134840.69010.000246982.4003109625.611291448.709003731152211333000dd85db55545bd6566f36b0fd3be9fd8555c36e&#13;
'''

    def _party_supplier(self, UBLExtensions):
        asp = SubElement(UBLExtensions, 'fe:AccountingSupplierParty')
        aac = SubElement(asp, 'cbc:AdditionalAccountID').text = "1"
        party = SubElement(aac, 'fe:Party')
        pi = SubElement(party, 'cac:PartyIdentification')
        SubElement(pi, 'cbc:ID', attrib={ "schemeAgencyID":"195", "schemeAgencyName":"CO, DIAN (Direccion de Impuestos y Aduanas Nacionales)", "schemeID":"31"}).text = "900373115"
        pn = SubElement(party, 'cac:PartyName')
        SubElement(pn, 'cbc:Name').text = "PJ - 900373115 - Adquiriente FE"
        pl = SubElement(party, 'fe:PhysicalLocation')
        addr = SubElement(pl, 'fe:Address')
        SubElement(addr, 'cbc:Department').text = "Distrito Capital"
        SubElement(addr, 'cbc:CitySubdivisionName').text = "Centro"
        SubElement(addr, 'cbc:CityName').text = "Bogotá"
        addrl = SubElement(addr, 'cac:AddressLine')
        SubElement(addrl, 'cbc:Line').text ="	carrera 8 Nº 6C - 78"
        addrc = SubElement(addr, 'cac:Country')
        SubElement(addrc, 'cbc:IdentificationCode').text = "CO"
        pts = SubElement(party, 'fe:PartyTaxScheme')
        SubElement(pts, 'cbc:TaxLevelCode').text = "0"
        SubElement(pts, 'cac:TaxScheme')
        ple = SubElement(party, 'fe:PartyLegalEntity')
        SubElement(ple, 'cbc:RegistrationName').text = "PJ - 900373115"

    def _party_customer(self, UBLExtensions):
        asp = SubElement(UBLExtensions, 'fe:AccountingCustomerParty')
        aac = SubElement(asp, 'cbc:AdditionalAccountID').text = "2"
        party = SubElement(aac, 'fe:Party')
        pi = SubElement(party, 'cac:PartyIdentification')
        SubElement(pi, 'cbc:ID', attrib={ "schemeAgencyID":"195", "schemeAgencyName":"CO, DIAN (Direccion de Impuestos y Aduanas Nacionales)", "schemeID":"22"}).text = "11333000"
        pl = SubElement(party, 'fe:PhysicalLocation')
        addr = SubElement(pl, 'fe:Address')
        SubElement(addr, 'cbc:Department').text = "Distrito Capital"
        SubElement(addr, 'cbc:CitySubdivisionName').text = "Centro"
        SubElement(addr, 'cbc:CityName').text = "Toribio"
        addrl = SubElement(addr, 'cac:AddressLine')
        SubElement(addrl, 'cbc:Line').text ="	carrera 8 Nº 6C - 46"
        addrc = SubElement(addr, 'cac:Country')
        SubElement(addrc, 'cbc:IdentificationCode').text = "CO"
        pts = SubElement(party, 'fe:PartyTaxScheme')
        SubElement(pts, 'cbc:TaxLevelCode').text = "0"
        SubElement(pts, 'cac:TaxScheme')
        person = SubElement(party, 'fe:Person')
        SubElement(person, 'cbc:FirstName').text = "Primer-N"
        SubElement(person, 'cbc:FamilyName').text = "Apellido-11333000"
        SubElement(person, 'cbc:MiddleName').text = "Segundo-N"

    def _tax_totals(self, tax_toal):
        id = 1
        for tax_line in self.tax_line_ids:
            tax_total = SubElement(UBLExtensions, 'fe:TaxTotal')
            SubElement(tax_toal, 'cbc:TaxAmount', attrib={ "currencyID": "COP"}) .text = 46982.4
            SubElement(tax_toal, 'cbc:TaxEvidenceIndicator').text = "false"
            ts = SubElement(tax_toal, 'fe:TaxSubtotal')
            SubElement(ts, 'cbc:TaxableAmount', attrib={ "currencyID":"COP"}).text = 1134840.69
            SubElement(ts, 'cbc:TaxAmount', attrib={"currencyID":"COP"}).text = 46982.4
            SubElement(ts, 'cbc:Percent').text = 4.14
            tc = SubElement(ts, 'cac:TaxCategory')
            tsc = SubElement(tc, 'cac:TaxScheme')
            SubElement(tsc, 'cbc:ID').text = "02"

    def _lmt(self, lmt):
        SubElement(lmt, 'cbc:LineExtensionAmount', attrib={ "currencyID":"COP"}).text = 1134840.69
        SubElement(lmt, 'cbc:TaxExclusiveAmount', attrib={"currencyID":"COP"}).text = 156608.01
        SubElement(lmt, 'cbc:PayableAmount', attrib={ "currencyID":"COP"}).text = 1291448.7

    def _lineas_detalle(self, UBLExtensions):
        line_number = 1
        if self.currency_id and self.company_id and self.currency_id != self.company_id.currency_id:
            currency_id = self.currency_id.with_context(date=self.date_invoice)
        for line in self.invoice_line_ids:
            line = SubElement(UBLExtensions, 'fe:InvoiceLine')
            if line.product_id.default_code == 'NO_PRODUCT':
                no_product = True
            SubElement(line, 'cbc:ID').text = line_number
            qty = round(line.quantity, 4)
            if not no_product:
                SubElement(line, 'cbc:IvoicedQuantity').text = qty
            if qty == 0 and not no_product:
                SubElement(line,'cbc:IvoicedQuantity').text = 1
            elif qty < 0:
                raise UserError("NO puede ser menor que 0")
            if not no_product:
                SubElement(line,'cbc:LineExtensionAmount', attrib={"currencyID": line.currency_id.code}).text = self.currency_id.round(line.price_subtotal)
            item = SubElement(line,'fe:Item').text = collections.OrderedDict()
            SubElement(item, 'cbc:Description').text = self._acortar_str(line.name, 1000) #descripción más extenza
            price = SubElement(line, 'fe:Price').text = collections.OrderedDict()
            SubElement(price, 'cbc:PriceAmount').text = round(line.price_unit, 6)

    def _UBLExtensions(self, taxInclude=False, MntExe=0):
        UBLExtensions = Element()
        rangos = SubElement(UBLExtensions, 'ext:UBLExtensions')
        self._rangos(rangos)
        firma = SubElement(UBLExtensions, 'ext:UBLExtensions')
        self._firma(firma)
        SubElement(UBLExtensions, 'cbc:UBLVersionID').text = "UBL 2.0"
        SubElement(UBLExtensions, 'cbc:ProfileID').text = "DIAN 1.0"
        SubElement(UBLExtensions, 'cbc:ID').text = self._id()
        uuid = SubElement(UBLExtensions, 'cbc:UUID', attrib={"schemeAgencyID":"195", "schemeAgencyName":"CO, DIAN (Direccion de Impuestos y Aduanas Nacionales)"})
        uuid.text = self._uuid()
        SubElement(UBLExtensions, 'cbc:IssueDate').text = "UBL 2.0"
        SubElement(UBLExtensions, 'cbc:IssueTime').text = "UBL 2.0"
        itc = SubElement(UBLExtensions, 'cbc:InvoiceTypeCode', attrib={"listAgencyID":"195", "listAgencyName":"CO, DIAN (Direccion de Impuestos y Aduanas Nacionales)", "listSchemeURI":"http://www.dian.gov.co/contratos/facturaelectronica/v1/InvoiceType"})
        itc.text = "1"
        SubElement(UBLExtensions, 'cbc:Note').text = self._note()
        SubElement(UBLExtensions, 'cbc:DocumentCurrencyCode').text = self._note()
        self._party_supplier(UBLExtensions)
        self._party_customer(UBLExtensions)
        self._tax_totals(UBLExtensions)
        lmt = SubElement(UBLExtensions, 'fe:LegalMonetaryTotal')
        self._lmt(lmt)
        self._lineas_detalle(UBLExtension)
        return IdDoc

    def _cufe(self):
        CUFE = SHA-1(NumFac + FecFac + ValFac + CodImp1 + ValImp1 + CodImp2 + ValImp2 + CodImp3 + ValImp3 + ValImp + NitOFE + TipAdq + NumAdq + ClTec)
