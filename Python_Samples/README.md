### edit_service_recycleTime.py

By default all services published to ArcGIS Enterprise on Kubernetes have their recycle time set to 00:00 UTC. This time may not be acceptable for all time zones. 

This sample script will edit the recycle time on all services in your organization. 

To run the script, provide the following information:

- Organization Url, https://organization.example.com/context
- Admin username
- Admin password 
- The new time you want your services to recycle in UTC. i.e. 04:00
- If you want to restart the service after the time is edited, enter yes. If not, enter no 

**Note:** at version 12.0 the service recycle option is not required as it's handled as part of the software when edits are made. However, at 11.5, the service needs to be restarted in order to see the change in recycle time. 
