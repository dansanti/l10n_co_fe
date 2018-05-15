# -*- coding: utf-8 -*-
{
    "name": """Facturación Electrónica para Colombia\
    """,
    'version': '0.0.1',
    'category': 'Localization/Colombia',
    'sequence': 12,
    'author':  'Daniel Santibáñez Polanco',
    'website': 'https://globalresponse.cl',
    'license': 'AGPL-3',
    'summary': '',
    'description': """
Facturación Electrónica para Colombia.
""",
    'depends': [
            'base',
            'account_invoicing',
            'purchase',
            'contacts',
            'l10n_co_commercial',
        ],
    'external_dependencies': {
        'python': [
            'xmltodict',
            'dicttoxml',
            'qrcode',
            'base64',
            'hashlib',
            'cchardet',
            'suds',#use suds-py3
            'urllib3',
            'signxml',
            'ast',
            'pysftp',
            'num2words',
            'xlsxwriter',
            'io',
        ]
    },
    'data': [
            'wizard/journal_config_wizard_view.xml',
            'views/account_journal_dian_document_class_view.xml',
            'views/journal_view.xml',
            'views/dian_menuitem.xml',
            'views/dian_document_class_view.xml',
            'views/caf.xml',
            'views/res_user.xml',
            'views/res_company.xml',
            'views/invoice_view.xml',

    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
