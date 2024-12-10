{
    'name': 'Mua Hang',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Yêu cầu mua hàng',
    'depends': ['base', 'hr', 'product', 'uom'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/purchase_view.xml',
        'views/purchase_line_view.xml',
        'data/sequence.xml',
    ],
    'demo': [],
    'css': [],
    'installable': True,
    'auto_install': False,
    'application': True,
}