"""Library module containing functions to retrieve course info through Canvas API.

API reference https://canvas.instructure.com/doc/api/submissions.html
Initially hacked from https://github.com/unsupported/canvas/tree/master/api/pull_course_grades

10.15.2016 tps Created module. Using Python version 2.7.12.
10.27.2016 tps Added exception handling around API call.
11.14.2016 tps Added pull_submissions_with_comments().
11.15.2016 tps Added pull_course_info().
11.15.2016 tps Fixed query_endpoint() to handle case of single JSON object
    being returned by Canvas API instead of a collection of objects.
11.15.2016 tps Added pull_assignment_info().
11.15.2016 tps Removed pull_course_student_submissions(). Use assignments API instead.
11.17.2016 tps Added pull_user_files(user_id).
11.18.2016 tps Added pull_user_profile(user_id).
11.18.2016 tps Added pull_submission(course_id, assignment_id, user_id).
11.18.2016 tps Changed BASE_URL so endpoint names don't need to start with '/'.
11.18.2016 tps Added pull_file_(file_id).
11.22.2016 tps Added RESULTS_PER_PAGE constant.
11.22.2016 tps Added pull_course_students,
11.22.2016 tps Removed obsolete pull functions.
11.22.2016 tps Shortened names for some functions.
11.23.2016 tps Fixed wrong domain in BASE_URL.
12.22.2016 tps Add requests for file & folder manipulation.
12.23.2016 tps Strip down so it's slightly simplified for upload demo example.
12.25.2016 tps Enable file & folder calls to masquerade as target user.
12.26.2016 tps Add functions to support file upload via URL.
01.10.2017 tps Add search_users_by_email().
03.29.2017 tps Add hint parameters to initiate_file_upload_via_url().
06.14.2017 tps Add pull_quota_info() for testing.
11.15.2018 tps Redo for changed behavior of Canvas API for file uploads.
12.20.2018 tps Add custom exception for Canvas API upload error.
"""

import requests         # http://docs.python-requests.org/

########### Endpoint constants ###########

ACCESS_TOKEN = 'secretkey'  # Development
BASE_URL = 'https://ourdomain.instructure.com/api/v1/'  # Production
REQUEST_HEADERS = {'Authorization':'Bearer %s' % ACCESS_TOKEN}

# Number of results to return per request.
RESULTS_PER_PAGE = 1000


######## Custom Exceptions ##########

class UploadDelegationException(Exception):
    pass


######## Utility Functions ##########

def query_endpoint(endpoint, request_params = {}):
    """Helper function to retrieve list of JSON objects from Canvas API endpoint.

    endpoint - Endpoint portion of request URL.
    request_params - Dictionary containing optional query parameters for request.

    Canvas API returns paged result sets, which is useful for Web apps but not
    really necessary here. To reduce number of API calls, I specify a large number 
    of results per page.
    """

    # Build full endpoint URL
    endpoint_url = BASE_URL + endpoint

    # Specify number of results to return in each request.
    submission_params = {'per_page':RESULTS_PER_PAGE}

    # Add additional request parameters from caller
    submission_params.update(request_params)
    # for key in request_params.keys():
    #     submission_params[key] = request_params[key]

    # Return this list filled with JSON dictionaries from Canvas API call.
    resp_data = []

    try:
        # Results are paged, so we have to keep requesting until we get all of them.
        while 1:
            resp = requests.get(endpoint_url, params=submission_params, headers=REQUEST_HEADERS)
            # print(resp.url)

            # The response might be a list of JSON dictionaries or it may be a single
            # JSON dictionary. If we have a list, we want to concatenate it to the
            # result list. If we have a single JSON dictionary, we want to append it
            # to the result list.
            resp_json = resp.json()
            if isinstance(resp_json, list):
                resp_data += resp_json
            else:
                resp_data.append(resp_json)

            # print "data count after page: %s" % len(resp_data)
            if 'next' in resp.links.keys():
                endpoint_url = resp.links['next']['url']
                # print endpoint_url
            else:
                break

    # If something bad happens while accessing Canvas API,
    # record the offending endpoint for debugging purposes.
    # A request error is catastrophic & there is no point in trying to continue.
    except Exception as ex:
        print('Error making API request at: ' + endpoint_url)
        print('Error: ' + ex)
        print("Status code: %s" % resp.status_code)
        print("Canvas response: " + resp.text)
        raise

    return resp_data

def multipart_post(upload_url, form_data, file_data):
    """Post multipart/file-data to an arbitrary URL.
    The response might contain a redirect to a confirmation URL, but we don't
    want this to happen automatically, because we usually want to capture the 
    JSON returned with the confirmation URL in a separate step.
    """
    return requests.post(upload_url, data = form_data, files = file_data, allow_redirects=False)

def canvas_post(canvas_url):
    """Make a post request to a Canvas URL.
    Used to query confirmation URL when doing a file upload.
    """
    resp = requests.post(canvas_url, headers = REQUEST_HEADERS)
    return resp.json()

def canvas_get(canvas_url):
    """Make an HTTP get request to a canvas URL.
    Used when querying a status URL when doing a file upload."""
    return requests.get(canvas_url, headers=REQUEST_HEADERS).json()


######## Data Entity Retrieval ##########

def pull_courses():
    """Retrieve list of JSON objects describing all the courses."""
    return query_endpoint('courses')

def pull_course_users(course_id):
    """Retrieve list of JSON users in a course."""
    return query_endpoint('courses/%s/users' % (course_id))

def pull_course_students(course_id):
    """Retrieve list of JSON users who are students enrolled in course."""

    # We just want to see the students
    request_params = {'enrollment_type[]':'student'}
    return query_endpoint('courses/%s/users' % (course_id), request_params)

def search_users_by_email(user_email):
    """Retrieve list of users with email matches."""
    return query_endpoint('accounts/self/users', {'search_term': user_email})


######## File & Folder Retrieval ##########

def pull_folders(user_id):
    """Retrieve JSON collection describing all user's folders
    """
    return query_endpoint('users/%s/folders' % (user_id))

def create_folder(user_id, parent_folder_path, folder_name):
    """Create folder in for Canvas user.
    Return JSON describing the newly created folder.
    """
    # Must masquerade as the user to create a folder for them.
    endpoint_url = BASE_URL + ('users/%s/folders?as_user_id=%s' % (user_id, user_id))
    form_data = {
        'name': folder_name,
        'parent_folder_path': parent_folder_path }
    resp = requests.post(endpoint_url, data = form_data, headers = REQUEST_HEADERS)
    return resp.json()

def delete_folder(user_id, folder_id):
    """Delete Canvas folder, including any files inside.
    Return JSON describing the deleted folder.
    """
    # Must masquerade as the user to delete their folders.
    endpoint_url = BASE_URL + ('folders/%s?as_user_id=%s&force=true' % (folder_id, user_id))
    resp = requests.delete(endpoint_url, headers=REQUEST_HEADERS)
    return resp.json()

def pull_files(folder_id):
    """Retrieve JSON collection listing files in the folder.
    """
    return query_endpoint('folders/%s/files' % (folder_id))

def pull_file(file_id):
    """Retrieve JSON for a single file upload."""
    return query_endpoint('files/%s' % (file_id))

def pull_user_files(user_id):
    """Retrieve JSON describing a user's file uploads."""
     
    # Include the user information.
    #request_params = { 'include[]':'usage_rights' } 
    # request_params = { 'include[]':'user' }
    return query_endpoint('users/%s/files/' % (user_id))

def pull_files_quota(user_id):
    """Retrieve file quota for the user."""
    # Must masquerade as the user to see their file quota.
    return query_endpoint('users/%s/files/quota' % (user_id), {'as_user_id':user_id})[0]['quota']

def pull_quota_info(user_id):
    """Retrieve total & used storage quota for the user."""
    # Must masquerade as the user to see their file quota.
    return query_endpoint('users/%s/files/quota' % (user_id), {'as_user_id':user_id})[0]

######## File Upload Functions ##########

def initiate_file_upload(user_id, folder_id, display_name, file_size = None):
    """Initiate a file upload.
    user_id -- Canvas ID of user whose account we want to upload to.
    folder_id -- Canvas ID of user's folder we want to upload file to.
    display_name -- Name we want to show for uploaded file in Canvas UI.
    file_size -- Size in bytes of file to upload. (optional)
    """
    # Must masquerade as the user to upload a file to their account.
    endpoint_url = BASE_URL + ('users/%s/files?as_user_id=%s' % (user_id, user_id))
    
    form_data = {
        'name': display_name,
        'parent_folder_id': folder_id }
    if (file_size is not None):
        form_data['size'] = file_size

    resp = requests.post(endpoint_url, data = form_data, headers = REQUEST_HEADERS)
    return resp.json()

def initiate_file_upload_via_url(user_id, folder_path, source_url, display_name, file_size = None, content_type = None):
# def initiate_file_upload_via_url(user_id, folder_id, source_url, display_name, file_size = None, content_type = None):
    """Initiate a file upload via URL.
    user_id -- Canvas ID of user whose account we want to upload to.
    folder_id -- Canvas ID of user's folder we want to upload file to.
    folder_path -- String specifying path of folder to store file in. A folder will be created if it doesn't exist.
    source_url -- URL of file to upload.
    display_name -- Name we want to show for uploaded file in Canvas UI.
    file_size -- (Optional) Hint for size of file in bytes.
    content_type -- (Optional) Hint for file content type.
    """
    # Must masquerade as the user to upload a file to their account.
    endpoint_url = BASE_URL + ('users/%s/files?as_user_id=%s' % (user_id, user_id))
    
    form_data = {
        'url' : source_url,
        'name': display_name,
        'parent_folder_path': folder_path }
        # 'parent_folder_id': folder_id }

    # Include hint parameters, if client provided any.
    if file_size is not None:
        form_data['size'] = file_size

    if content_type is not None:
        form_data['content_type'] = content_type

    resp = requests.post(endpoint_url, data = form_data, headers = REQUEST_HEADERS)
    # print('endpoint: %s status code: %s' % (endpoint_url, resp.status_code))
    respJson = resp.json()
    print(respJson)

    # 11.19.2018 tps Upload behavior has a possible step 2 which we might need to do.
    if 'upload_url' in respJson:
        print("Initiate upload delegation")
        resp2 = requests.post(respJson['upload_url'], data=respJson['upload_params'])

        # 12.07.2018 tps Sometimes this post fails with a 502 bad gateway error
        print('status code: %s response: %s' % (resp2.status_code, resp2.text))
        if (resp2.status_code == 502):
            raise UploadDelegationException('Canvas upload delegation failed with status code: %s response: %s' % (resp2.status_code, resp2.text))

        # API return value expected to be either a valid file descriptor or an error.
        # Report the error to the client. Otherwise, client needs the response to the
        # 1st request, which contains the progress URL.
        resp2json = resp2.json()
        print(resp2json)
        if ('error' in resp2json):
            respJson = resp2json

    return respJson
    # return resp.json()