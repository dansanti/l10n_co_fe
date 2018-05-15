# -*- coding: utf-8 -*-
from odoo import fields, models, api
from odoo.tools.translate import _
import ast
from datetime import datetime
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DTF
import logging
_logger = logging.getLogger(__name__)

class ColaEnvio(models.Model):
    _name = "dian.cola_envio"

    doc_ids = fields.Char(
            string="Id Documentos",
        )
    model = fields.Char(
            string="Model destino",
        )
    user_id = fields.Many2one(
            'res.users',
        )
    tipo_trabajo = fields.Selection(
            [
                    ('pasivo', 'pasivo'),
                    ('envio', 'Envío'),
                    ('consulta', 'Consulta')
            ],
            string="Tipo de trabajo",
        )
    active = fields.Boolean(
            string="Active",
            default=True,
        )
    n_atencion = fields.Char(
            string="Número atención",
        )
    date_time = fields.Datetime(
            string='Auto Envío al DIAN',
        )
    send_email = fields.Boolean(
            string="Auto Enviar Email",
            default=False,
        )

    def enviar_email(self, doc):
        att = doc._create_attachment()
        body = 'XML de Intercambio DTE: %s' % (doc.document_number)
        subject = 'XML de Intercambio DTE: %s' % (doc.document_number)
        doc.message_post(
            body=body,
            subject=subject,
            partner_ids=[doc.partner_id.id],
            attachment_ids=att.ids,
            message_type='comment',
            subtype='mt_comment',
        )
        if doc.partner_id.dte_email == doc.partner_id.email:
            return
        values = {
            'email_from': doc.company_id.dte_email,
            'email_to': doc.partner_id.dte_email,
            'auto_delete': False,
            'model' : self.model,
            'body': body,
            'subject': subject,
            'attachment_ids': att.ids,
        }
        send_mail = self.env['mail.mail'].create(values)
        send_mail.send()

    def _procesar_tipo_trabajo(self):
        docs = self.env[self.model].browse(ast.literal_eval(self.doc_ids))
        if self.tipo_trabajo == 'pasivo':
            if docs[0].dian_xml_request and docs[0].dian_xml_request.state in [ 'Aceptado', 'Enviado', 'Rechazado']:
                self.unlink()
                return
            if self.date_time and datetime.now() >= datetime.strptime(self.date_time, DTF):
                try:
                    envio_id = docs.do_dte_send()
                    if envio_id.dian_send_ident:
                        self.tipo_trabajo = 'consulta'
                except Exception as e:
                    _logger.warning('Error en Envío automático')
                    _logger.warning(str(e))
                docs.get_dian_result()
            return
        if docs[0].dian_message and docs[0].dian_result in ['Proceso', 'Reparo', 'Rechazado']:
            if self.send_email and docs[0].dian_result in ['Proceso', 'Reparo']:
                for doc in docs:
                    self.enviar_email(doc)
            self.unlink()
            return
        if self.tipo_trabajo == 'consulta':
            try:
                docs.ask_for_dte_status()
            except Exception as e:
                _logger.warning("Error en Consulta")
                _logger.warning(str(e))
        elif self.tipo_trabajo == 'envio' and (not docs[0].dian_xml_request or not docs[0].dian_xml_request.dian_send_ident or docs[0].dian_xml_request.state not in [ 'Aceptado', 'Enviado']):
            try:
                envio_id = docs.do_dte_send()
                if envio_id.dian_send_ident:
                    self.tipo_trabajo = 'consulta'
                docs.get_dian_result()
            except Exception as e:
                _logger.warning("Error en envío Cola")
                _logger.warning(str(e))

    @api.model
    def _cron_procesar_cola(self):
        ids = self.search([('active','=',True)])
        if ids:
            for c in ids:
                c._procesar_tipo_trabajo()
