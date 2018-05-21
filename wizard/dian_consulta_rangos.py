# -*- coding: utf-8 -*-
from odoo import api, models, fields
from odoo.tools.translate import _
from odoo.exceptions import UserError
import random
import logging

try:
    from suds.client import Client
except:
    _logger.warning("no se ha cargado suds")

url = 'https://facturaelectronica.dian.gov.co/servicios/B2BIntegrationEngine-servicios/FacturaElectronica/consultaResolucionesFacturacion.wsdl'

_logger = logging.getLogger(__name__)

class DIANConsultaRangos(models.TransientModel):
    _name = 'dian.consulta_rangos'

    def consulta(self):
        try:
            ssnp = self.env['dian.xml.envio'].with_context({'company_id': self.env.user.company_id}).security_header(self.env.user_id)
            _server = Client(url)
            _server.set_options(soapheaders=ssnp)
            respuesta = _server.service.ConsultaResolucionesFacturacion(
                self.env.user.company_id.vat,
                self.env.user.company_id.serialNumber,
                self.env.user.company_id.software_id,
            )
            result = respuesta.data
        except Exception as e:
            result = str(e)
        self.result = result

    result = fields.Text(
        string="Resultado",
        compute='consulta',
    )
    type = fields.Selection(
            [
                ('ConsultaResoluciones', 'Consulta Resoluciones'),
                ('RangoFacturacion', 'Rango Facturación'),
                ('ResolucionesFacturacion', 'Resoluciones Facturación'),
            ],
            string="Tipo de consulta",
            default='ConsultaResoluciones',
        )
    company_id = fields.Many2one(
            'res.company',
            string='Company',
            required=False,
            default=lambda self: self.env.user.company_id,
        )
