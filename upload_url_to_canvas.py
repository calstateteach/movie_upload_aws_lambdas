""" AWS Lambda function that copies movie file at a URL to Canvas via the URL upload API.
API Reference: https://canvas.instructure.com/doc/api/file.file_uploads.html

Accepts a dictionary containing the following keys:

file_url -- String specifying publicly accessible URL for the file to upload to Canvas.
file_display_name -- String specifying name to display for the file in the Canvas Web app.
                     If there is already a file with the same name in the user's account,
                     it will be overwritten
user_email -- String specifying email associated with the Canvas user account that is
              the destination for the file.
file_size -- Integer size in bytes of the file to upload. (Optional)
callback_url -- String specifying publicly accessible URL which receives a POST request 
                when the file upload is done. (Optional)
status_url -- (Optional) String specifying a Canvas upload status URL generated from a previous
               call to this function. If it exists, instead of initiating an upload, continue
               polling the Canvas URL until the upload is ready or an error occurs or a timeout
               occurs.

Returns a dictionary containing the original parameters keys plus:

status_url -- String containing Canvas upload status URL.
status_flag -- Integer flag specifying status of the upload:
               STATUS_ERROR, STATUS_QUOTA_EXCEEDED, STATUS_INITIATED or STATUS_POLLING.
status_msg -- If status_flag is STATUS_ERROR, this is a
              description of the error, possibly including a stack trace.
              If status_flag is STATUS_INITIATED or STATUS_POLLING, this is
              the Canvas status URL.
              if status_flag is STATUS_QUOTA_EXCEEDED, this is a message specifying the account's
              quota limit.

03.29.2017 tps Created from begin_upload_to_canvas.py (Python 2.7).
04.03.2017 tps Added handling for different types of error return values from Canvas API
               depending on whether or not a file size hit is provided.
04.05.2017 tps Add status URL to log, so there is some way to recover status URL after this
               process finishes.
05.15.2017 tps Per request from GS, make function re-entrant by adding a Canvas status URL to the
               input parameters. If status_url input parameter exists, poll the Canvas status URL
               until the upload is ready or an error occurs.
05.17.2017 tps Use integer status flags to indicate status of Canvas upload.
06.14.2017 tps Return specific status flag for upload exceeding account space quota.
06.15.2017 tps Moved Canvas user ID lookup functions to canvas_api_helper.py.
11.15.2018 tps Redo for changed behavior of Canvas API file uploads.
12.20.2018 tps Catch specific Canvas upload API exception.
"""

import callback_helper
import canvas_api
import canvas_api_helper
import param_helper

import boto3
import json
import traceback


######## Constants ##########

# Target folder for uploads in Canvas user's account.
UPLOAD_FOLDER_PARENT_PATH = 'my files'
UPLOAD_FOLDER_NAME = 'VideoUploads'
UPLOAD_FOLDER_FULL_PATH = '/'.join((UPLOAD_FOLDER_PARENT_PATH, UPLOAD_FOLDER_NAME))

LAMBDA_ARN = 'arn:aws:lambda:somelambdaarn'    # For Testing


######## Custom Validation Exceptions ##########

class FileSizeExceedsQuotaException(Exception):
    pass

class CanvasUploadException(Exception):
    pass

class LambdaCallException(Exception):
    pass

########### Helper Canvas API Functions ###########

def get_user_folders_dict(user_id):
    """Retrieve dictionary of user's folders, where key is folder's full path & value is folder's Canvas ID.
    """
    return { folder['full_name'] : folder['id'] for folder in canvas_api.pull_folders(user_id) }


def get_upload_folder_id(user_id):
    """Retrieve Canvas ID of user's video upload folder.
    Create the upload folder in Canvas if it does not already exist.
    """
    folder_id = None
    folder_dict = get_user_folders_dict(user_id)
    if UPLOAD_FOLDER_FULL_PATH in folder_dict:
        folder_id = folder_dict[UPLOAD_FOLDER_FULL_PATH]
    else:
        folder_json = canvas_api.create_folder(user_id, UPLOAD_FOLDER_PARENT_PATH, UPLOAD_FOLDER_NAME)
        folder_id = folder_json['id']
    return folder_id



########### Main Function ###########

def upload_to_canvas(param_dict):
    return_dict = {}

    # If client already provided a status URL,
    # our job is to continue polling the status URL until upload is done.
    # Otherwise, we initiate the upload.
    status_url = param_dict.get('status_url')
    if isinstance(status_url, basestring) and (status_url != ''):
        return_dict = initiate_polling(param_dict)
    else:
        return_dict = initiate_upload(param_dict)
    return return_dict


def initiate_upload(param_dict):
    return_dict = {}    # Return value

    print(param_dict)   # Log parameter values

    # See if client provided a callback URL, which we can use to report
    # errors & transfer status.
    callback_url = param_dict.get('callback_url')  # Optional parameter

    # See if the client provided the size in bytes of the upload file, which we can
    # use as a hint for the Canvas API.
    upload_file_size = param_dict.get('file_size')

    try:
        # Unpack parameters
        file_url = param_helper.validate(param_dict, 'file_url')
        display_name = param_helper.validate(param_dict, 'file_display_name')
        user_email = param_helper.validate(param_dict, 'user_email')

        # Resolve user ID
        user_id = canvas_api_helper.get_canvas_user_id(user_email)
        print('User ID: %s' % user_id)

        # # Make sure there is enough room to upload the file.
        # # We might not know the file size.
        # if upload_file_size is not None:
        #     quota_size = canvas_api.pull_files_quota(user_id)
        #     if upload_file_size > quota_size:
        #         raise FileSizeExceedsQuotaException('File size exceeds user\'s quota.')

        # Make sure an uploads folder exists for the user.
        # folder_id = get_upload_folder_id(user_id)
        # print('Upload folder id: %s' % folder_id)

        # Initiate URL upload
        # resp = canvas_api.initiate_file_upload_via_url(user_id, folder_id, file_url, display_name, upload_file_size)
        resp = canvas_api.initiate_file_upload_via_url(user_id, UPLOAD_FOLDER_FULL_PATH, file_url, display_name, upload_file_size)
        print (resp)

        # There's at least 2 ways this API call can fail.
        # If the HTTP response status code is 200, there should be an upload_status
        # field in the response that we can look at, which might have an error status.
        # If the HTTP response status is 400, we'll get a structure with just a 'message'
        # key, containing an error message. This error condition seems to be triggered
        # when we've provided a file size hint for the upload. In this case we can use
        # the absence of an 'upload_status' key as an error flag.

        # 11.19.2018 tps Check for file quota limit when a size hint was given
        if ('message' in resp) and (resp['message'] == 'file size exceeds quota'):
            raise FileSizeExceedsQuotaException(resp['message'])

        # 11.19.2018 tps Check for file quota limit when a size hint was not given
        if ('error' in resp) and ('file size exceeds quota limits' in resp['error']):
            raise FileSizeExceedsQuotaException(resp['error'])

        # 11.19.2018 tps Some other error from step 2.
        if ('error' in resp):
            raise CanvasUploadException(resp['error'])

        # 11.15.2018 tps Check for reasonable API return status, new behavior
        if 'progress' not in resp:
            raise CanvasUploadException("File upload call did not return a progress object.")
        if 'url' not in resp['progress']:
            raise CanvasUploadException("File upload call did not return a progress URL.")
        #? Test for file quota exceeded error
        #? Test for other non-predictable errors reported.

        # # Check for reasonable API return status.
        # if 'upload_status' not in resp:
        #     # In this case, we should at least get a 'message' field that tells us what went wrong.
        #     err_msg = resp['message']
        #     if  canvas_api_helper.is_quota_exceeded_msg(err_msg):
        #         raise FileSizeExceedsQuotaException(err_msg)
        #     else:
        #         raise CanvasUploadException(err_msg)
        # if resp['upload_status'] != 'pending':
        #     raise CanvasUploadException('Error initiating upload. Canvas returned: %s ' % json.dumps(resp))

        # Launch process that polls for upload status
        poll_params = param_dict.copy()
        status_url = resp['progress']['url']
        # status_url = resp['status_url']
        poll_params['status_url'] = status_url
        return_dict = initiate_polling(poll_params)

        # For clients calling synchronously, return status flag indicating this call
        # initiated the upload.
        return_dict = callback_helper.make_callback_dictionary(
            return_dict, callback_helper.STATUS_INITIATED, status_url)

    except FileSizeExceedsQuotaException as ex:
        # Log the error
        print('%s %s' % (type(ex), ex))

        # Report upload error due to user's file quota exceeded
        err_msg = canvas_api_helper.make_quota_exceeded_message(user_id)

        # Report the error to the callback URL
        return_dict = callback_helper.make_callback_dictionary(
            param_dict, callback_helper.STATUS_QUOTA_EXCEEDED, err_msg)
        callback_helper.make_callback_post(callback_url, return_dict)

    except (param_helper.MissingParameterException,
            param_helper.ParameterTypeException,
            canvas_api_helper.UserNotFoundException,
            CanvasUploadException,
            LambdaCallException,
            canvas_api.UploadDelegationException) as ex:

        # Log the error
        print('%s %s' % (type(ex), ex))

        # Report the error to the callback URL
        return_dict = callback_helper.make_callback_dictionary(
            param_dict, callback_helper.STATUS_ERROR, ex.message)
        callback_helper.make_callback_post(callback_url, return_dict)

    except Exception as ex:
        # Attempt to report unexpected exception to callback
        # and to default error handler.

        # Build a description for the unexpected exception.
        error_description = '\n'.join((
            'Exception type: %s' % type(ex),
            'Exception: %s' % ex,
            traceback.format_exc()
        ))

        # Log the unexpected exception. We do this now because the following attempt to
        # make the callback might itself throw another exception.
        print(error_description)

        # Report the error to the callback URL
        return_dict = callback_helper.make_callback_dictionary(
            param_dict, callback_helper.STATUS_ERROR, error_description)
        callback_helper.make_callback_post(callback_url, return_dict)

        # Let the default error handler see this error.
        raise

    return return_dict


def initiate_polling(lambda_params):
    """Launch the AWS Lambda function that polls Canvas for the status of a URL file upload.
    """

     # Call Lambda function asynchronously
    # client = boto3.client('lambda', region_name = 'us-west-2')    # Shouldn't need to specify region when installed.
    client = boto3.client('lambda')
    response = client.invoke(
        FunctionName=LAMBDA_ARN,
        InvocationType='Event',
        Payload=json.dumps(lambda_params)
    )

    # Check for reasonable Lambda call return status
    if response['StatusCode'] not in range(200, 300):
        raise LambdaCallException('Lambda call returned bad status code: %s ' % json.dumps(response))

    # Check for error notification header.
    if 'x-amz-function-error' in response['ResponseMetadata']['HTTPHeaders']:
        raise LambdaCallException('Lambda call returned x-amz-function-error header: %s' % json.dumps(response))

    # If Lambda function called successfully, return the parameter dictionary it was sent.
    return callback_helper.make_callback_dictionary(
        lambda_params, callback_helper.STATUS_POLLING, lambda_params['status_url'])


########### Lambda Entry Point ###########

def lambda_handler(event, context):
    return upload_to_canvas(event)
