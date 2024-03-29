# AWS Lambda Functions for Canvas Uploads

This respository contains Python scripts for AWS Lambda functions that manage Canvas file uploads via URLs.

## Overview
When the Lambda function is called with a file's URL, it initiates the upload to Canvas & starts polling the Canvas API for the upload status. The Lambda returns one of the following results by making an HTTP POST to a callback URL provided by the client:

* Upload completed successfully.
* Upload is pending after a timeout period of 4 minutes.
* The upload failed because the target account does not have enough storage space.
* An unexpected, unrecoverable error occurred.

If the upload is pending, the client can call the Lambda again, supplying the Canvas upload status URL as a parameter. This re-entrant call continues polling for the upload status & posts the outcome to the callback URL

## Calling the Lambda Function
The Lambda function is expected to be called asynchronously & accepts a parameter dictionary with the following values:

|Parameter Name|Type|Use|
|--------------|----|---|
|`file_url`|String|Publicly accessible URL for the file to upload to Canvas.|
|`file_display_name`|String|Name to display for the file in the Canvas Web app. If there is already a file with the same name in the user's account, it will be overwritten|
|`user_email`|String|Email associated with the Canvas user account that is the destination for the file.|
|`file_size`|Integer|Size in bytes of the file to upload. (Optional)|
|`callback_url`|String|Publicly accessible URL which receives a POST request when the file upload is done. (Optional) |
|`status_url`|String|(Optional) A Canvas upload status URL generated by a prior call to this function. If this parameter is included, the function continues polling this URL instead of initiating a file upload.|

The client may pass in additional client-specific parameters. The Lambda function will include them in the POST to the callback URL.

## Callback POST
When the file transfer is complete, the callback URL receives a POST request containing the original parameters plus the following data:

|Key|Value|
|---|-----|
|`status_url`|String containing Canvas upload status URL for the file transfer.|
|`status_flag`|An integer flag specifying the status of the upload.|
|`status_msg`|A status message, depending upon the state of `status_flag`.|

### `status_flag` Values

|Value|Status|Result|`status_msg` Contents|
|-----|------|------|---------------------|
|1|STATUS_ERROR|An unexpected & unrecoverable error has occurred.|Error message.|
|3|STATUS_PENDING|The upload is pending.|The Canvas upload status URL.|
|4|STATUS_READY|The upload is done.|Canvas's JSON descriptor for the file upload.|
|5|STATUS_QUOTA_EXCEEDED|The upload failed due to hitting the account's storage limit.|"File size exceeds quota. Quota: 5,242,880,000 bytes. Quota used: 5,170,095,303 bytes."|

## Source Files

|File|Description|
|----|-----------|
|*upload\_url\_to\_canvas.py*|Top level module for Lambda function that initiates upload to Canvas.|
|*poll_canvas\_upload.py*|Top level module for Lambda function that polls Canvas API for the upload status of a file.|
|*canvas\_api.py*|Functions that call the Canvas API.|
|*canvas\_api\_helper.py*|Helper functions for data retrieved through the Canvas API.|
|*param\_helper.py*|Helper module for validating Lambda's input parameters.|
|*callback\_helper.py*|Helper functions for making HTTP POST to the callback URL.|

### Dependencies
* [Python requests library](http://docs.python-requests.org/)

## Lambda Functions Configuration

The Lambda service is really implemented by 2 Lambda functions, which are both expected to be called asynchronously. The 1st function initiates the file upload. It then invokes a 2nd function that polls for the upload status & posts to the callback URL when a result has been reached.

### 1) Function that initiates upload

|Item|Setting|
|----|-------|
|Source file|*upload\_url\_to\_canvas.py*|
|Handler|*upload\_url\_to\_canvas.lambda_handler*|
|Runtime|Python 2.7|
|Memory|128MB|
|Timeout|1 minute|

### 2) Function that polls for upload status

|Item|Setting|
|----|-------|
|Source file: *poll\_canvas\_upload.py*|
|Handler|*poll\_canvas\_upload.lambda_handler*|
|Runtime|Python 2.7|
|Memory|128MB|
|Timeout|5 minutes (maximum timeout)|

## Authors

* **Terence Shek** - *Programmer* - [tpshek](https://github.com/tpshek/)

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details
