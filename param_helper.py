"""Helper module for validating required function parameters.
05.16.2017 tps Created. Python 2.7.
"""

######## Custom Validation Exceptions ##########

class MissingParameterException(Exception):
    pass

class ParameterTypeException(Exception):
    pass


######## Validation Functions ##########

def validate(parameter_dictionary, parameter_name):
    """Verify that parameter dictionary contains a particular value
    of string type. Throw custom validation exception if there's
    a problem. Return parameter's value if it exists & is a string."""
    if parameter_name not in parameter_dictionary:
        raise MissingParameterException('Missing "%s" parameter.' % parameter_name)
    parameter_value = parameter_dictionary[parameter_name]
    if not isinstance(parameter_value, basestring):
        raise ParameterTypeException('"%s" parameter is not a string.' % parameter_name)
    return parameter_value

