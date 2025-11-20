# Required imports
import getpass
import requests
import json
import time
import datetime
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_token(OrganizationURL, tokenExpiration, adminUser, adminPass):
    tokenUrl = '{}/sharing/rest/generateToken?f=json'.format(OrganizationURL)

    payload = {
        'username': adminUser,
        'password': adminPass,
        'referer': 'referer',
        'expiration': tokenExpiration,
        'f': 'json'
    }
    print("\nRequesting Token...")
    res = requests.post(tokenUrl, data=payload, verify=False)
    #print(res.json())

    try:
        return res.json()['token']

    except KeyError:
        raise Exception('Could Not Fetch Token with Authentication Inputs')
#
def EditServiceJson(OrganizationURL, token, NewrecycleStartTime):
    serviceUrl = "{}/admin/services?f=pjson&token={}".format(OrganizationURL, token)
    serviceResp = requests.get(serviceUrl, verify=False)
    folders = serviceResp.json()["folders"]
    rootServices = serviceResp.json()["services"]
    #
    #edit services in root dir 
    for s in rootServices:
        print("/" + s['serviceName'] + "/" + s['type'])
        recycleUrl = "{}/admin/services/{}.{}?f=json&token={}".format(OrganizationURL, s['serviceName'], s['type'], token)
        recycleResp = requests.get(recycleUrl, verify=False)
        jsonData = json.loads(recycleResp.content)
        #
        print("\tChanging recycleStartTime from " + jsonData['recycleStartTime'] + " to " + NewrecycleStartTime)
        jsonData['recycleStartTime'] = NewrecycleStartTime
        Update1 = json.dumps(jsonData)
        #
        editServiceUrl = "{}/admin/services/{}.{}/edit?f=json&token={}".format(OrganizationURL, s['serviceName'], s['type'], token)
        UpdatePayload = {
                'f': 'json',
                'service': Update1 
        }
        editServiceResp = requests.post(editServiceUrl, data=UpdatePayload, verify=False)
        print("\t" + editServiceResp.json()['status'] + "\n")

    # loop through the folders and edit services in folders
    for f in folders:
        # Hosted services don’t have recycling, so we can skip this folder.
        if f == 'Hosted': 
            print("skipping " + f + " folder")
        else: 
            # find service names in the folder
            FserviceUrl = "{}/admin/services/{}?f=pjson&token={}".format(OrganizationURL, f, token)
            Fresp = requests.get(FserviceUrl, verify=False)
            services = Fresp.json()['services']
            # loop through services in folder and get service names and types
            for s in services:
                print(f + "/" + s['serviceName'] + "/" + s['type'])
                recycleUrl = "{}/admin/services/{}/{}.{}?f=json&token={}".format(OrganizationURL, f, s['serviceName'], s['type'], token)
                recycleResp = requests.get(recycleUrl, verify=False)
                jsonData = json.loads(recycleResp.content)
                #
                print("\tChanging recycleStartTime from " + jsonData['recycleStartTime'] + " to " + NewrecycleStartTime)
                jsonData['recycleStartTime'] = NewrecycleStartTime
                Update1 = json.dumps(jsonData)
                #
                editServiceUrl = "{}/admin/services/{}/{}.{}/edit?f=json&token={}".format(OrganizationURL, f, s['serviceName'], s['type'], token)
                UpdatePayload = {
                        'f': 'json',
                        'service': Update1 
                }
                editServiceResp = requests.post(editServiceUrl, data=UpdatePayload, verify=False)
                print("\t" + editServiceResp.json()['status'] + "\n")
#   
def restartServices(OrganizationURL, token, restart):
    if restart == 'true':
        serviceUrl = "{}/admin/services?f=pjson&token={}".format(OrganizationURL, token)
        serviceResp = requests.get(serviceUrl, verify=False)
        #
        folders = serviceResp.json()["folders"]
        rootServices = serviceResp.json()["services"]
        #
        startServiceList = []
        for s in rootServices:
            #
            statusUrl = "{}/admin/services/{}.{}/status?f=pjson&token={}".format(OrganizationURL, s["serviceName"], s["type"], token)
            statusResp = requests.get(statusUrl, verify=False)
            #
            if statusResp.json()['configuredState'] and statusResp.json()['realTimeState'] == 'STARTED':
                print("Restarting..." + s["serviceName"] + "/" + s['type'])
                #########################################################################
                #  
                stopSvcUrl = "{}/admin/services/{}.{}/stop".format(OrganizationURL, s["serviceName"], s["type"])
                startSvcUrl = "{}/admin/services/{}.{}/start".format(OrganizationURL, s["serviceName"], s["type"])
                #payload = {'f': 'json'}
                payloadsync = {'f': 'json', 'token': token}
                payloadasync = {'f': 'json', 'async': 'true', 'token': token}
                print("\tStopping service")
                stopSvcResp = requests.post(stopSvcUrl, data=payloadsync ,verify=False)
                #
                print("\tStarting service")
                startSvcResp = requests.post(startSvcUrl, data=payloadasync ,verify=False)
                #
                startServiceList.append(startSvcResp.json()['jobsUrl'])
                #
                #########################################################################
            else:
                print("Skipping..." + s["serviceName"] + "/" + s["type"] + " is STOPPED!")

        #loop through folders 
        for f in folders:
            if f == 'Hosted':
                # Hosted services don’t have recycling, so we can skip this folder.
                print("Skipping " + f + " folder")
            else:
                FserviceUrl = "{}/admin/services/{}?f=pjson&token={}".format(OrganizationURL, f, token)
                Fresp = requests.get(FserviceUrl, verify=False)
                services = Fresp.json()['services']
                #
                for s in services:
                    #
                    statusUrl = "{}/admin/services/{}/{}.{}/status?f=pjson&token={}".format(OrganizationURL, f, s["serviceName"], s["type"], token)
                    statusResp = requests.get(statusUrl, verify=False)
                    if statusResp.json()['configuredState'] and statusResp.json()['realTimeState'] == 'STARTED':
                        #
                        print("Restarting..." + f + "/" + s['serviceName'] + "/" + s['type'])
                        #########################################################################
                        #  
                        stopSvcUrl = "{}/admin/services/{}/{}.{}/stop".format(OrganizationURL, f, s["serviceName"], s["type"])
                        startSvcUrl = "{}/admin/services/{}/{}.{}/start".format(OrganizationURL, f, s["serviceName"], s["type"])
                        #payload = {'f': 'json'}
                        payloadsync = {'f': 'json', 'token': token}
                        payloadasync = {'f': 'json', 'async': 'true', 'token': token}
                        print("\tStopping service")
                        stopSvcResp = requests.post(stopSvcUrl, data=payloadsync ,verify=False)
                        #
                        print("\tStarting service")
                        startSvcResp = requests.post(startSvcUrl, data=payloadasync ,verify=False)
                        #
                        startServiceList.append(startSvcResp.json()['jobsUrl'])
                        #
                        #########################################################################

                    else:
                        print("Skipping..." + f + "/" + s['serviceName'] + "/" + s['type'] + " is STOPPED!")
                #
        print("\nGetting status from starting services...\n")
        for job in startServiceList:
            jobUrl = job + "?f=json&token={}".format(token)
            time.sleep(5) #sleep 5 sec before getting the status
            jobResp = requests.get(jobUrl, verify=False)
            getStatus = jobResp.json()['status']
            getSvcName = jobResp.json()['resource']['name']
            while getStatus != 'COMPLETED':
                #
                getNewresp = requests.get(jobUrl, verify=False)
                if getNewresp.json()['status'] == 'COMPLETED':
                    getStatus = 'COMPLETED'
                else:
                    #
                    print("\t " + getSvcName + " - " + str(getNewresp.json()['status']))
                    time.sleep(5) #sleep 5 sec
            print("  " + getSvcName + " - started successfully")
    else: 
        print("Not restarting services")
#

if __name__ == '__main__':

    #OrganizationURL = 'https://organization.example.com/context'
    #adminUser = 'myuser'
    #adminPass = 'myuserpassword'
    OrganizationURL = input("Enter the Organization URL and context (i.e. https://organization.example.com/context): ")
    adminUser = input("Admin username: ")
    adminPass = getpass.getpass(prompt="Admin password: ")
    tokenExpiration = '60'
    
    #NewrecycleStartTime = "04:00"
    NewrecycleStartTime = input("Enter the time to recycle services in UTC (i.e. 04:00): ")

    #restart = "true"
    restart = input("Restart services when done? yes or no: ")

    starttime = datetime.datetime.now() 

    #get_token
    mytoken = get_token(OrganizationURL, tokenExpiration, adminUser, adminPass)

    # edit recycle time
    EditServiceJson(OrganizationURL, mytoken, NewrecycleStartTime)
    
    # restart services
    # to manually restart services use false
    if restart == "yes":
        restartServices(OrganizationURL, mytoken, "true")
    else:
        restartServices(OrganizationURL, mytoken, "false")
    
    endtime = datetime.datetime.now()

    print("elapsed time: " + str(endtime - starttime))

#############################################################################
    # UTC 00:00 = 19:00 / 7pm ET  / 6pm CT  / 5pm MT  / 4pm PT 
    # UTC 01:00 = 20:00 / 8pm ET  / 7pm CT  / 6pm MT  / 5pm PT 
    # UTC 02:00 = 21:00 / 9pm ET  / 8pm CT  / 7pm MT  / 6pm PT  
    # UTC 03:00 = 22:00 / 10pm ET / 9pm CT  / 8pm MT  / 7pm PT 
    # UTC 04:00 = 23:00 / 11pm ET / 10pm CT / 9pm MT  / 8pm PT  
    # UTC 05:00 = 00:00 / 12am ET / 11pm CT / 10pm MT / 9pm PT 
    # UTC 06:00 = 01:00 / 1am ET  / 12am CT / 11pm MT / 10pm PT 
    # UTC 07:00 = 02:00 / 2am ET  / 1am CT  / 12am MT / 11pm PT  
    # UTC 08:00 = 03:00 / 3am ET  / 2am CT  / 1am MT  / 12am PT  
    # UTC 09:00 = 04:00 / 4am ET  / 3am CT  / 2am MT  / 1am PT  
    # UTC 10:00 = 05:00 / 5am ET  / 4am CT  / 3am MT  / 2am PT  
    # UTC 11:00 = 06:00 / 6am ET  / 5am CT  / 4am MT  / 3am PT  
    # UTC 12:00 = 07:00 / 7am ET  / 6am CT  / 5am MT  / 4am PT
    # UTC 13:00 = 08:00 / 8am ET  / 7am CT  / 6am MT  / 5am PT
    # UTC 14:00 = 09:00 / 9am ET  / 8am CT  / 7am MT  / 6am PT 
    # UTC 15:00 = 10:00 / 10am ET / 9am CT  / 8am MT  / 7am PT  
    # UTC 16:00 = 11:00 / 11am ET / 10am CT / 9am MT  / 8am PT 
    # UTC 17:00 = 12:00 / 12pm ET / 11am CT / 10am MT / 9am PT 
    # UTC 18:00 = 13:00 / 1pm ET  / 12pm CT / 11am MT / 10am PT 
    # UTC 19:00 = 14:00 / 2pm ET  / 1pm CT  / 12pm MT / 11am PT 
    # UTC 20:00 = 15:00 / 3pm ET  / 2pm CT  / 1pm MT  / 12pm PT 
    # UTC 21:00 = 16:00 / 4pm ET  / 3pm CT  / 2pm MT  / 1pm PT 
    # UTC 22:00 = 17:00 / 5pm ET  / 4pm CT  / 3pm MT  / 2pm PT  
    # UTC 23:00 = 18:00 / 6pm ET  / 5pm CT  / 4pm MT  / 3pm PT  
#############################################################################
