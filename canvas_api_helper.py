"""Module for helper functions that wrap Canvas API call.
06.15.2017 tps Created. Python 2.7.
"""
import canvas_api

######## Constants ##########

# 06.14.2017 Beginning of error message returned by Canvas API for file upload
# operation that fails due to running out of storage for user.
# This string is expected to appear in error messages when initiating a
# file upload or polling a status URL.
QUOTA_MESSAGE = 'file size exceeds quota'


######## Custom Validation Exceptions ##########

class UserNotFoundException(Exception):
    pass


######## Modules Functions ##########

def get_canvas_user_id(user_email):
    """Retrieve the Canvas user ID associated with the given email.
    Throw exception if no match found."""
    search_results = canvas_api.search_users_by_email(user_email)
    user_id = find_exact_match_for_login_id(search_results, user_email)
    if user_id is None:
        raise UserNotFoundException('User %s not found.' % user_email)
    return user_id

def find_exact_match_for_login_id(search_results, target_login_id):
    """The Canvas user search API results do not return only exact matches,
    so this function filters search results for an exact match only.

    search_results -- List of user objects returned by Canvas user search API.
    target_login_id -- Canvas login ID that we want to find an exact match for.

    Returns Canvas ID of matching user or None if no exact match is found.
    """
    return_dict = { user['login_id']: user['id'] for user in search_results}
    return return_dict.get(target_login_id)

def is_quota_exceeded_msg(msg):
    """Test if user's file quota was exceeded by seeing if message string corresponds
    to Canvas API error message for file upload error due to exceeding user's file quota.
    """
    return msg.startswith(QUOTA_MESSAGE)

def make_quota_exceeded_message(user_id):
    """Build an error message meant to be returned when file upload fails
    due to quota limit exceeded on user's account.
    """
    quota_info = canvas_api.pull_quota_info(user_id)
    return "File size exceeds quota. Quota: {0:,d} bytes. Quota used: {1:,d} bytes.". \
        format(quota_info['quota'], quota_info['quota_used'])
