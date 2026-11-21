"""Audited read-only operations. Never infer safety from tool annotations or code."""
READ_COMMANDS=frozenset(('ping','drawing-info','drawing-get-variables','entity-count',
                         'entity-list','entity-get','layer-list','block-list','block-get-attributes'))
READ_TOOLS={
    'drawing':frozenset(('info','get_variables')),
    'entity':frozenset(('list','count','get')),
    'layer':frozenset(('list',)),
    'block':frozenset(('list','get_attributes')),
    'system':frozenset(('status',)),
}

def readonly_tool(name,arguments):
    return isinstance(arguments,dict) and arguments.get('operation') in READ_TOOLS.get(name,())
