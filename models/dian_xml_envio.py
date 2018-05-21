# -*- coding: utf-8 -*-
from odoo import fields, models, api
from odoo.tools.translate import _
from datetime import datetime, timedelta, date
from lxml import etree
import pytz
import collections
import logging
_logger = logging.getLogger(__name__)
try:
    import urllib3
    urllib3.disable_warnings()
    pool = urllib3.PoolManager()
except:
    _logger.warning("no se ha cargado urllib3")

try:
    from suds.client import Client
    from suds.sax.element import Element
    from suds.sax.attribute import Attribute
except:
    _logger.warning("no se ha cargado suds")
try:
    import xmltodict
except ImportError:
    _logger.warning('Cannot import xmltodict library')
try:
    from signxml import XMLSigner, methods
except ImportError:
    _logger.warning('Cannot import signxml')

connection_status = {
    '0': 'Upload OK',
    '1': 'El Sender no tiene permiso para enviar',
    '2': 'Error en tamaño del archivo (muy grande o muy chico)',
    '3': 'Archivo cortado (tamaño <> al parámetro size)',
    '5': 'No está autenticado',
    '6': 'Empresa no autorizada a enviar archivos',
    '7': 'Esquema Invalido',
    '8': 'Firma del Documento',
    '9': 'Sistema Bloqueado',
    'Otro': 'Error Interno.',
}

class DIANXMLEnvio(models.Model):
    _name = 'dian.xml.envio'

    name = fields.Char(
            string='Nombre de envío',
            required=True,
            readonly=True,
            states={'draft': [('readonly', False)]},
        )
    xml_envio = fields.Text(
            string='XML Envío',
            required=True,
            readonly=True,
            states={'draft': [('readonly', False)]},
        )
    state = fields.Selection(
            [
                    ('draft', 'Borrador'),
                    ('NoEnviado', 'No Enviado'),
                    ('Enviado', 'Enviado'),
                    ('Aceptado', 'Aceptado'),
                    ('Rechazado', 'Rechazado'),
            ],
            default='draft',
        )
    company_id = fields.Many2one(
            'res.company',
            string='Compañia',
            required=True,
            default=lambda self: self.env.user.company_id.id,
            readonly=True,
            states={'draft': [('readonly', False)]},
        )
    dian_xml_response = fields.Text(
            string='DIAN XML Response',
            copy=False,
            readonly=True,
            states={'NoEnviado': [('readonly', False)]},
        )
    dian_send_ident = fields.Text(
            string='DIAN Send Identification',
            copy=False,
            readonly=True,
            states={'draft': [('readonly', False)]},
        )
    dian_receipt = fields.Text(
            string='DIAN Mensaje de recepción',
            copy=False,
            readonly=False,
            states={'Aceptado': [('readonly', False)], 'Rechazado': [('readonly', False)]},
        )
    user_id = fields.Many2one(
            'res.users',
            string="Usuario",
            helps='Usuario que envía el XML',
            readonly=True,
            states={'draft': [('readonly', False)]},
        )
    invoice_ids = fields.One2many(
            'account.invoice',
            'dian_xml_request',
            string="Facturas",
            readonly=True,
            states={'draft': [('readonly', False)]},
        )

    @api.multi
    def name_get(self):
        result = []
        for r in self:
            name = r.name + " Código Envío: %s" % r.dian_send_ident if r.dian_send_ident else r.name
            result.append((r.id, name))
        return result

    def password_hash(self, digest=False):
        pass_hash = hashlib.new('sha256', company_id.software_id)
        if digest:
            return base64b64encode(pass_hash.digest()).decode()
        return pass_hash.hexdigest()


    def security_header(self, user_id,  Nonce=False, digestPassword=False):
        ssnp = Element("wsse:Security")
        ssnp.append(Attribute('SOAP-ENV:mustUnderstand', 'true'))
        ssnp.attributes.append(Attribute('xmlns:wsse',"http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"))
        ssnp.attributes.append(Attribute('xmlns:wsu',"http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"))
        UNT = Element('wsse:UsernameToken')
        UNT.attributes.append(Attribute('Id',"UsernameToken-1"))
        Username = Element('wsse:Username')
        Username.setText(self.company_id.software_id)
        Password = Element('wsse:Password')
        pass_hash =  self.password_hash()
        if digestPassword:
            Password.attributes.append(Attribute('Type','http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#Digest'))
            pass_hash =  self.password_hash(digest=True)
        Password.setText(pass_hash)
        UNT.append(Username)
        UNT.append(Password)
        if Nonce:
            NONCE = Element('wsse:Nonce')
            NONCE.setText(base64.b64encode(str(random.random()).encode()).decode())
            NONCE.attributes.append(Attribute('EncodingType',"http://docs.oasis-open.org/wss/2004/01/oasis200401-wss-soap-message-security1.0#Base64Binary"))
            formato='%Y-%m-%dT%H:%M:%S.523Z'
            tz = pytz.timezone('America/Bogota')
            CREATED = Element('wsu:Created').setText(datetime.now(tz).strftime(formato))
            UNT.append(NONCE)
            UNT.append(CREATED)
        ssnp.append(UNT)
        return ssnp

    def init_params(self):
        params = collections.OrderedDict()
        signature_d = self.user_id.get_digital_signature(self.company_id)
        if not signature_d:
            raise UserError(_('''There is no Signer Person with an \
        authorized signature for you in the system. Please make sure that \
        'user_signature_key' module has been installed and enable a digital \
        signature, for you or make the signer to authorize you to use his \
        signature.'''))
        params['rutSender'] = signature_d['subject_serial_number'][:8]
        params['dvSender'] = signature_d['subject_serial_number'][-1]
        params['rutCompany'] = self.company_id.vat[2:-1]
        params['dvCompany'] = self.company_id.vat[-1]
        params['archivo'] = (self.name, self.xml_envio, "text/xml")
        return params

    def procesar_recepcion(self, retorno, respuesta_dict):
        if respuesta_dict['RECEPCIONDTE']['STATUS'] != '0':
            _logger.warning(connection_status[respuesta_dict['RECEPCIONDTE']['STATUS']])
        else:
            retorno.update({'state': 'Enviado','dian_send_ident': respuesta_dict['RECEPCIONDTE']['TRACKID']})
        return retorno

    def send_xml(self, post='/cgi_dte/UPL/DTEUpload'):
        retorno = { 'state': 'NoEnviado' }
        if not self.company_id.dian_mode:
            raise UserError(_("Not Service provider selected!"))
        token = self.get_token( self.user_id, self.company_id )
        url = 'https://palena.dian.cl'
        if self.company_id.dian_mode == 'DIANCERT':
            url = 'https://maullin.dian.cl'
        headers = {
            'Accept': 'image/gif, image/x-xbitmap, image/jpeg, image/pjpeg, application/vnd.ms-powerpoint, application/ms-excel, application/msword, */*',
            'Accept-Language': 'es-cl',
            'Accept-Encoding': 'gzip, deflate',
            'User-Agent': 'Mozilla/4.0 (compatible; PROG 1.0; Windows NT 5.0; YComp 5.0.2.4)',
            'Referer': '{}'.format(self.company_id.website),
            'Connection': 'Keep-Alive',
            'Cache-Control': 'no-cache',
            'Cookie': 'TOKEN={}'.format(token),
        }
        params = self.init_params()
        multi = urllib3.filepost.encode_multipart_formdata(params)
        headers.update({'Content-Length': '{}'.format(len(multi[0]))})
        response = pool.request_encode_body('POST', url+post, params, headers)
        retorno.update({ 'dian_xml_response': response.data })
        if response.status != 200:
            return retorno
        respuesta_dict = xmltodict.parse(response.data)
        retorno = self.procesar_recepcion(retorno, respuesta_dict)
        self.write(retorno)
        return retorno

    def get_send_status(self, user_id=False):
        user_id = user_id or self.user_id
        token = self.get_token( user_id, self.company_id )
        url = server_url[self.company_id.dian_mode] + 'QueryEstUp.jws?WSDL'
        _server = Client(url)
        rut = self.invoice_ids.format_vat( self.company_id.vat, con_cero=True)
        respuesta = _server.service.getEstUp(
                rut[:8],
                str(rut[-1]),
                self.dian_send_ident,
                token,
            )
        result = { "dian_receipt" : respuesta }
        resp = xmltodict.parse( respuesta )
        result.update({ "state": "Enviado" })
        if resp['DIAN:RESPUESTA']['DIAN:RESP_HDR']['ESTADO'] == "-11":
            if resp['DIAN:RESPUESTA']['DIAN:RESP_HDR']['ERR_CODE'] == "2":
                status =  {'warning':{'title':_('Estado -11'), 'message': _("Estado -11: Espere a que sea aceptado por el DIAN, intente en 5s más")}}
            else:
                status =  {'warning':{'title':_('Estado -11'), 'message': _("Estado -11: error 1Algo a salido mal, revisar carátula")}}
        if resp['DIAN:RESPUESTA']['DIAN:RESP_HDR']['ESTADO'] == "EPR":
            result.update({ "state": "Aceptado" })
            if resp['DIAN:RESPUESTA']['DIAN:RESP_BODY']['RECHAZADOS'] == "1":
                result.update({ "state": "Rechazado" })
        elif resp['DIAN:RESPUESTA']['DIAN:RESP_HDR']['ESTADO'] in ["RCT", 'RFR']:
            result.update({ "state": "Rechazado" })
            _logger.warning(resp)
            status = {'warning':{'title':_('Error RCT'), 'message': _(resp['DIAN:RESPUESTA']['DIAN:RESP_HDR']['GLOSA'])}}
        self.write( result )
