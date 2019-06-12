""" AWS Lambda function that polls for the status of a file being uploaded to Canvas
 via the URL method. This is expected to be called asynchronously from upload_url_to_canvas.py,
 the module that initiates the upload.

Accepts a dictionary requiring the following keys:

status_url -- String containing Canvas upload status URL.
callback_url -- Optional. String. Do HTTP POST of results of polling to this URL.
user_email -- Optional. String containing email address specifying user whose account
              we are doing the upload for. If specified, this is used to return the account's
              file quota information if the file quota is reached.

The parameter dictionary can contain other keys, which are ignored but passed through to the return dictionary.

Returns a dictionary containing the original parameters keys plus:

status_flag -- Integer flag specifying status of the upload:
               STATUS_ERROR, STATUS_QUOTA_EXCEEDED, STATUS_PENDING or STATUS_READY.
status_msg -- If status_flag is STATUS_READY, this is the JSON string returned by the Canvas API,
              describing the properties of the upload. If status_flag is STATUS_ERROR, this is a
              description of the error, possibly including a stack trace. If status_flag is 
              STATUS_PENDING, this is a message saying how long the function has been polling.
              if status_flag is STATUS_QUOTA_EXCEEDED, this is a message specifying the account's
              quota limit.



05.15.2017 tps Created from upload_url_to_canvas.py. Python 2.7 
05.17.2017 tps Use integer status flags to return upload status to client.
06.14.2017 tps Return specific status for file quota exceeded.
11.15.2018 tps Redo for changed behavior of Canvas file upload API. The structure returned by the
    status URL is now expected to look like:

  {
    "id": 5432,
    "context_id": 654,
    "context_type": "User",
    "user_id": 654,
    "tag": "upload_via_url",
    "completion": 100,
    "workflow_state": "completed",
    "created_at": "2018-11-14T21:22:08Z",
    "updated_at": "2018-11-14T21:28:20Z",
    "message": null,
    "url": "https://ourdomain.instructure.com/api/v1/progress/5432",
    "results": {
      "id": 8765
    }
  }

"""

import callback_helper
import canvas_api
import canvas_api_helper
import param_helper

import json
import time
import traceback

######## Constants ##########

WAIT_INTERVAL = 15  # Number of seconds to wait between polling for status.
MAX_WAIT = 240  # Maximum number of seconds to wait for upload to complete.
                # Maximum timeout for Lambda function is 5 minutes.

######## Custom Validation Exceptions ##########

class UploadTimeoutException(Exception):
    pass

class CanvasUploadException(Exception):
    pass

######## Main Function ##########

def poll(param_dict):
    """Stop waiting when either the upload status is no longer pending
    or we run out of time to wait.
    """
    max_wait_time = time.time() + MAX_WAIT

    print(param_dict)   # Show parameters, for diagnostic purposes.

    return_dict = {}    # Populate with return values.

    # See if client provided a callback URL, which we can use to report
    # errors & transfer status.
    callback_url = param_dict.get('callback_url')  # Optional parameter

    try:

        # Unpack status URL
        status_url = param_helper.validate(param_dict, 'status_url')

        status_resp = None  # Populate with response from calling the status URL.
        upload_status = None  # Populate with final upload status from Canvas API.
        while True:
            # Check on the status of the upload.
            status_resp = canvas_api.canvas_get(status_url)
            print(status_resp)

            # 11.19.2018 tps No documented errors are returned by the Canvas API's progress URL.

            # # Handle error message returned by progress URL
            # if 'error' in status_resp:
            #     # The only time I've encountered this condition is for the quota limit exceeded,
            #     # which we can try to detect by looking at the error message.
            #     if 'file size exceeds quota limits' in status_resp['error']:
            #         # Return error message about user's quota usage.
            #         user_id = canvas_api_helper.get_canvas_user_id(param_dict.get('user_email'))
            #         err_msg = canvas_api_helper.make_quota_exceeded_message(user_id)
            #
            #         return_dict = callback_helper.make_callback_dictionary(
            #             param_dict, callback_helper.STATUS_QUOTA_EXCEEDED, err_msg)
            #         callback_helper.make_callback_post(callback_url, return_dict)
            #         break
            #     else:
            #         raise CanvasUploadException(
            #             'Progress URL %s returned error: %s'
            #             % (status_url, status_resp['error']))

            # Make sure progress URL returned a status field to inspect.
            if 'workflow_state' not in status_resp:
                raise CanvasUploadException(
                    'Progress URL %s missing workflow_state field'
                    % status_url)

            # # Again, API might not return an upload_status field.
            # if 'upload_status' not in status_resp:
            #     raise CanvasUploadException(
            #         'Canvas returned upload error: "%s" Status URL: %s'
            #         % (status_resp['message'], status_url))

            # upload_status = status_resp['upload_status']
            upload_status = status_resp['workflow_state']
            # if upload_status != 'pending':      # Done waiting?
            if upload_status not in ('queued', 'running'):       # Stop waiting when we've reached an end state
                break

            if time.time() > max_wait_time:     # Can't keep waiting any longer.
                raise UploadTimeoutException(
                    'File upload still pending after more than %s seconds. Status URL: %s'
                    % (MAX_WAIT, status_url))

            # Give Canvas some time to do its thing.
            time.sleep(WAIT_INTERVAL)

        # If we got this far, workflow status should be "complete" or "failed"
        if upload_status == 'completed':
            # Inform client of normal upload result.
            # Return the file descriptor of the upload, which means another call to Canvas,
            # which means another chance for an error.
            statusMsg = ''  # We'll fill this in later
            try:
                fileDescriptor = canvas_api.pull_file(status_resp['results']['id'])[0]
                statusMsg = json.dumps(fileDescriptor)
            except Exception as ex:
                # Log the error so we can diagnose it later
                print('Error getting file descriptor for successful upload: %s %s' % (type(ex), ex))

                # Let client know something went wrong, even though this isn't a fatal error.
                statusMsg = "Error when trying to retrieve Canvas file descriptor for the upload."

            return_dict = callback_helper.make_callback_dictionary(
                param_dict, callback_helper.STATUS_READY, statusMsg)
            callback_helper.make_callback_post(callback_url, return_dict)

        elif upload_status == 'failed':
            # Haven't been able to make this condition occur,
            # but assume there'd be a useful message.
            err_msg = status_resp['message']
            return_dict = callback_helper.make_callback_dictionary(
                param_dict, callback_helper.STATUS_ERROR, err_msg)
            callback_helper.make_callback_post(callback_url, return_dict)

        else:   # If we got here, we got an unknown workflow state, so I really don't know what to do.
            err_msg = "Progress URL returned unknown workflow_state of %s." % upload_status
            return_dict = callback_helper.make_callback_dictionary(
                param_dict, callback_helper.STATUS_ERROR, err_msg)
            callback_helper.make_callback_post(callback_url, return_dict)


        # if upload_status == 'ready':
        #     # Inform client of normal upload result.
        #     attachment = json.dumps(status_resp['attachment'])
        #     return_dict = callback_helper.make_callback_dictionary(
        #         param_dict, callback_helper.STATUS_READY, attachment)
        #     callback_helper.make_callback_post(callback_url, return_dict)
        # else:
        #     # Assume we got an upload status of "failed"
        #     err_msg = status_resp['message']
        #
        #     # Return specific status code for file quota exceeded message.
        #     if  canvas_api_helper.is_quota_exceeded_msg(err_msg):
        #
        #         # Return error message about user's quota usage.
        #         user_id = canvas_api_helper.get_canvas_user_id(param_dict.get('user_email'))
        #         err_msg = canvas_api_helper.make_quota_exceeded_message(user_id)
        #
        #         return_dict = callback_helper.make_callback_dictionary(
        #             param_dict, callback_helper.STATUS_QUOTA_EXCEEDED, err_msg)
        #         callback_helper.make_callback_post(callback_url, return_dict)
        #
        #     # Inform client of unexpected upload error.
        #     else:
        #         raise CanvasUploadException('Canvas returned upload error: "%s"' % err_msg)


    except UploadTimeoutException as ex:
        # We had to quit because the upload was taking too long.
        return_dict = callback_helper.make_callback_dictionary(
            param_dict, callback_helper.STATUS_PENDING, ex.message)
        callback_helper.make_callback_post(callback_url, return_dict)

    except (param_helper.MissingParameterException,
            param_helper.ParameterTypeException,
            CanvasUploadException) as ex:

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

        # Log the unexpected exception. We do this now because the following
        # attempt to make the callback might itself throw another exception.
        print(error_description)

        # Report the error to the callback URL
        return_dict = callback_helper.make_callback_dictionary(
            param_dict, callback_helper.STATUS_ERROR, error_description)
        callback_helper.make_callback_post(callback_url, return_dict)

        # Let the default error handler see this error.
        raise

    return return_dict

########### Lambda Entry Point ###########

def lambda_handler(event, context):
    return poll(event)
