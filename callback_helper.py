"""Module for helper functions for performing HTTP POST to callback URL.

02.07.2017 tps Created.
05.16.2017 tps Add test to skip blank URL.
05.17.2017 tps Use integer status flags instead of strings to indicate upload status.
06.14.2017 tps Added return status for upload failure due to file quota exceeded.
"""

# import canvas_api
import requests
import traceback


######## Status Flag Constants ##########
STATUS_INITIATED = 0
STATUS_ERROR = 1
STATUS_POLLING = 2
STATUS_PENDING = 3
STATUS_READY = 4
STATUS_QUOTA_EXCEEDED = 5

def make_callback_dictionary(param_dict, status_flag, status_msg):
    """Utility function that adds extra return values to parameter dictionary."""
    callback_dict = param_dict.copy()
    callback_dict['status_flag'] = status_flag
    callback_dict['status_msg'] = status_msg
    return callback_dict

def make_callback_post(callback_url, param_dict):
    """Utility function that makes the callback, which is an HTTP POST."""

    # It's OK to skip the callback altogether if the client didn't give us a callback URL.
    if (callback_url is not None) and isinstance(callback_url, basestring) and (callback_url != ''):

        # Swallow errors trying to reach callback URL. There's nothing we can do except try to log it.
        try:
            callback_resp = requests.post(callback_url, data=param_dict)
            print('Callback URL: %s Status code: %s' % (callback_url, callback_resp.status_code))
        except Exception as ex:
            print('Error making callback:')
            error_description = '\n'.join((
                'Exception type: %s' % type(ex),
                'Exception: %s' % ex,
                traceback.format_exc()
            ))
            print(error_description)