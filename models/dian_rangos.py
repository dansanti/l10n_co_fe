# -*- coding: utf-8 -*-
from odoo import models, fields, api, SUPERUSER_ID
from odoo.tools.translate import _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

try:
    import xmltodict
except ImportError:
    pass

try:
    import base64
except ImportError:
    pass

class caf(models.Model):
    _name = 'dian.rangos'

    @api.depends('caf_file')
    def _compute_data(self):
        for caf in self:
            if caf:
                caf.load_caf()

    name = fields.Char(
            string='File Name',
           readonly=True,
           compute='_get_filename',
        )
    filename = fields.Char(
            string='File Name',
        )
    caf_file = fields.Binary(
            string='rangos XML File',
            filters='*.xml',
            required=True,
            help='Upload the rangos XML File in this holder',
        )
    issued_date = fields.Date(
            string='Issued Date',
            compute='_compute_data',
            store=True,
        )
    dian_document_class = fields.Integer(
            string='DIAN Document Class',
            compute='_compute_data',
            store=True,
        )
    start_nm = fields.Integer(
            string='Start Number',
            help='rangos Starts from this number',
            compute='_compute_data',
            store=True,
        )
    final_nm = fields.Integer(
            string='End Number',
            help='rangos Ends to this number',
            compute='_compute_data',
            store=True,
        )
    status = fields.Selection(
            [
                ('draft', 'Draft'),
                ('in_use', 'In Use'),
                ('spent', 'Spent'),
            ],
            string='Status',
            default='draft',
            help='''Draft: means it has not been used yet. You must put in in used
in order to make it available for use. Spent: means that the number interval
has been exhausted.''',
        )
    rut_n = fields.Char(
            string='RUT',
            compute='_compute_data',
            store=True,
        )
    company_id = fields.Many2one(
            'res.company',
            string='Company',
            required=False,
            default=lambda self: self.env.user.company_id,
        )
    sequence_id = fields.Many2one(
            'ir.sequence',
            string='Sequence',
        )
    use_level = fields.Float(
            string="Use Level",
            compute='_used_level',
        )
    _sql_constraints = [
                ('filename_unique','unique(filename)','Error! Filename Already Exist!'),
            ]

    @api.onchange("caf_file",)
    def load_caf(self, flags=False):
        if not self.caf_file:
            return
        result = self.decode_caf()['AUTORIZACION']['rangos']['DA']
        self.start_nm = result['RNG']['D']
        self.final_nm = result['RNG']['H']
        self.dian_document_class = result['TD']
        self.issued_date = result['FA']
        self.rut_n = 'CL' + result['RE'].replace('-','')
        if self.rut_n != self.company_id.vat.replace('L0','L'):
            raise UserError(_(
                'Company vat %s should be the same that assigned company\'s vat: %s!') % (self.rut_n, self.company_id.vat))
        elif self.dian_document_class != self.sequence_id.dian_document_class_id.dian_code:
            raise UserError(_(
                '''DIAN Document Type for this rangos is %s and selected sequence associated document class is %s. This values should be equal for DTE Invoicing to work properly!''') % (self.dian_document_class, self.sequence_id.dian_document_class_id.dian_code))
        if flags:
            return True
        self.status = 'in_use'
        self._used_level()

    def _used_level(self):
        for r in self:
            if r.status not in [ 'draft' ]:
                folio = r.sequence_id.number_next_actual
                try:
                    if folio > r.final_nm:
                        r.use_level = 100
                    elif folio < r.start_nm:
                        r.use_level = 0
                    else:
                        r.use_level = 100.0 * ((int(folio) - r.start_nm) / float(r.final_nm - r.start_nm + 1))
                except ZeroDivisionError:
                    r.use_level = 0
            else:
                r.use_level = 0

    def _get_filename(self):
        for r in self:
            r.name = r.filename

    def decode_caf(self):
        post = base64.b64decode(self.caf_file).decode('ISO-8859-1')
        post = xmltodict.parse(post.replace(
            '<?xml version="1.0"?>','',1))
        return post

class sequence_caf(models.Model):
    _inherit = "ir.sequence"

    def get_qty_available(self, folio=None):
        folio = folio or self._get_folio()
        try:
            cafs = self.get_caf_files(folio)
        except:
            cafs = False
        available = 0
        folio = int(folio)
        if cafs:
            for c in cafs:
                if folio >= c.start_nm and folio <= c.final_nm:
                    available += c.final_nm - folio
                elif folio <= c.final_nm:
                    available +=  (c.final_nm - c.start_nm) + 1
                if folio > c.start_nm:
                    available +=1
        return available

    def _qty_available(self):
        for i in self:
            i.qty_available = i.get_qty_available()

    dian_document_class_id = fields.Many2one(
            'dian.document_class',
            string='Tipo de Documento',
        )
    is_dte = fields.Boolean(
            string='IS DTE?',
            related='dian_document_class_id.dte',
        )
    dte_caf_ids = fields.One2many(
            'dian.rangos',
            'sequence_id',
            string='DTE Caf',
        )
    qty_available = fields.Integer(
            string="Quantity Available",
            compute="_qty_available"
        )
    forced_by_caf = fields.Boolean(
            string="Forced By rangos",
            default=True,
        )

    def _get_folio(self):
        return self.number_next_actual

    def get_caf_file(self, folio=False):
        folio = folio or self._get_folio()
        caffiles = self.get_caf_files(folio)
        if not caffiles:
            raise UserError(_('''No hay caf disponible para el documento %s folio %s. Por favor solicite suba un rangos o solicite uno en el DIAN.''' % (self.name, folio)))
        for caffile in caffiles:
            if int(folio) >= caffile.start_nm and int(folio) <= caffile.final_nm:
                return caffile.decode_caf()
        msg = '''No Hay caf para el documento: {}, está fuera de rango . Solicite un nuevo rangos en el sitio \
www.dian.cl'''.format(folio)
        raise UserError(_(msg))

    def get_caf_files(self, folio=None):
        '''
            Devuelvo caf actual y futuros
        '''
        folio = folio or self._get_folio()
        if not self.dte_caf_ids:
            raise UserError(_('''No hay rangoss disponibles para la secuencia de %s. Por favor suba un rangos o solicite uno en el DIAN.''' % (self.name)))
        cafs = self.dte_caf_ids
        sorted(cafs, key=lambda e: e.start_nm)
        result = []
        for caffile in cafs:
            if int(folio) <= caffile.final_nm:
                result.append(caffile)
        if result:
            return result
        return False

    def update_next_by_caf(self, folio=None):
        folio = folio or self._get_folio()
        menor = False
        cafs = self.get_caf_files(folio)
        if not cafs:
            raise UserError(_('No quedan rangoss para %s disponibles') % self.name)
        for c in cafs:
            if not menor or c.start_nm < menor.start_nm:
                menor = c
        if menor and int(folio) < menor.start_nm:
            self.sudo(SUPERUSER_ID).write({'number_next': menor.start_nm})

    def _next_do(self):
        number_next = self.number_next
        if self.implementation == 'standard':
            number_next = self.number_next_actual
        folio = super(sequence_caf, self)._next_do()
        if self.forced_by_caf and self.dte_caf_ids:
            self.update_next_by_caf(folio)
            actual = self.number_next
            if self.implementation == 'standard':
                actual = self.number_next_actual
            if number_next +1 != actual: #Fue actualizado
                number_next = actual
            folio = self.get_next_char(number_next)
        return folio
