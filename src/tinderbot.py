# -----------------------------------------------------------------------------
#
# Python wrapper built on top on the Tinder API.
#
# References:
# https://gist.github.com/rtt/10403467
# https://gist.github.com/rtt/5a2e0cfa638c938cca59
#
# To get facebook token:
# https://www.facebook.com/dialog/oauth?client_id=464891386855067&
# redirect_uri=https://www.facebook.com/connect/login_success.html&
# scope=basic_info,email,public_profile,user_about_me,user_activities,
# user_birthday,user_education_history,user_friends,user_interests,user_likes,
# user_location,user_photos,user_relationship_details&response_type=token
#
# To get facebook id:
# http://findmyfacebookid.com
#
#------------------------------------------------------------------------------

import json
import requests
import datetime
import os
import urllib
import signal
import sys


BOT_NAME = "TinderBot"
HEADERS = {
	"app_version"  : "4",
	"content-type" : "application/json",
	"platform"     : "android",
	"user-agent"   : "Tinder/4.0.9 (iPhone; iOS 8.1.1; Scale/2.00)",
}
HOST = "https://api.gotinder.com"
STORE_BASE_PATH = "{0}/tinderStore".format( os.environ["HOME"] )
TIME_FORMAT = "%H:%M:%S"


class TinderBotException( Exception ):
	pass


class TinderBot( object ):
	def __init__( self ):
		self.__headers = HEADERS
		self.__profile = {}
		self.__storePath = ""
		self.__people = {}
		self.__matches = []
		self.__matchedPeople = {}
		self.__blocks = {}
		self.__remainingLikes = sys.maxsize
		self.__cancelling = False
		signal.signal( signal.SIGINT, self.__signalHandler )

	def getPeople( self ):
		return self.__people

	def getMatches( self ):
		return self.__matches

	def getMatchedPeople( self ):
		return self.__matchedPeople

	def __signalHandler( self, signal, frame):
		self.__cancelling = True
		self.__printMsg( "Cancelling ..." )

	def __printMsg( self, msg ):
		time = datetime.datetime.now().strftime( TIME_FORMAT )
		msg = "[{0}] {1}: {2}".format( time, BOT_NAME, msg )
		print( msg )

	def __validResponse( self, response ):
		if response.status_code != 200:
			msg = "Error in request: {0}".format( response.status_code )
			self.__printMsg( msg )
			return False
		return True

	def __requestProfile( self ):
		self.__printMsg( "Requesting your profile ..." )
		response = requests.get( "{0}/profile".format( HOST ),
			headers=self.__headers )
		if not self.__validResponse( response ):
			return
		self.__profile = response.json()
		self.__printMsg( "Your profile was loaded." )
		self.__storePath = "{0}/{1}_{2}_store".format( STORE_BASE_PATH,
			self.__profile["name"], self.__profile["_id"] )
		self.__printMsg( "Store path set." )

	def __loadPeople( self ):
		if not os.path.isdir( self.__storePath ):
			self.__printMsg( "Cannot load people: Store doesn't exist" )
			return
		peopleDirs = os.listdir( self.__storePath )
		for personDir in peopleDirs:
			if self.__cancelling:
				self.__cancelling = False
				return
			profileFile = "{0}/{1}/profile.json".format( self.__storePath,
				personDir )
			if not os.path.exists( profileFile ):
				continue
			with open(profileFile, "r") as inFile:
				person = json.load( inFile )
			self.__people[person["_id"]] = person
			msg = "{0}'s profile loaded.".format( person["name"] )
			self.__printMsg( msg )
		msg = "{0} people loaded.".format( len( self.__people ) )
		self.__printMsg( msg )

	def authenticate( self, token, id_ ):
		data = json.dumps( {"facebook_token": token, "facebook_id": id_} )
		self.__printMsg( "Authenticating ..." )
		response = requests.post( "{0}/auth".format( HOST ),
			headers=self.__headers, data=data )
		if not self.__validResponse( response ):
			# if 500 your facebook token might be out of date
			return
		self.__headers["X-Auth-Token"] = response.json()["token"]
		self.__userId = response.json()["user"]["_id"]
		self.__printMsg( "Athentication succesfully." )
		self.__requestProfile()
		self.__loadPeople()

	def __saveProfile( self, person, profileDir ):
		profileDestination = "{0}/profile.json".format( profileDir )
		self.__printMsg( "Saving {0}'s profile ...".format( person["name"] ) )
		with open(profileDestination, "w") as outFile:
			json.dump( person, outFile )
	
	def __savePhotos( self, person, photosDir ):
		self.__printMsg( "Saving {0}'s photos ...".format( person["name"] ) )
		for photo in person["photos"]:
			url = photo["url"]
			photoDestination = "{0}/{1}".format( photosDir, photo["fileName"] )
			urllib.request.urlretrieve( url, photoDestination )

	def __indexPerson( self, person, indexDir ):
		self.__printMsg( "Indexing {0} in {1} ...".format(
			person["name"], indexDir.rsplit("/",1)[1] ) )
		if not person["photos"]:
			self.__printMsg( "Cannot index {0}: No pictures.".format(
				person["name"] ) )
			return
		for photo in person["photos"][::-1]:
			# if no valid main the first photo is used
			if photo.get("main"):
				# it may not have the key main
				break
		photoDestination = "{0}/{1}_{2}/photos/{3}".format(
			self.__storePath, person["name"], person["_id"], photo["fileName"] )
		_, extension = os.path.splitext( photo["fileName"] )
		indexLink = "{0}/{1}_{2}{3}".format( indexDir, person["name"],
			person["_id"], extension )
		if os.path.exists( indexLink ):
			os.remove( indexLink )
		os.symlink( photoDestination, indexLink )

	def __savePerson( self, person ):
		# Profile
		profileDir = "{0}/{1}_{2}".format( self.__storePath, person["name"],
			person["_id"] )
		if not os.path.isdir( profileDir ):
			os.makedirs( profileDir )
		self.__saveProfile( person, profileDir )
		# Photos
		photosDir = "{0}/{1}_{2}/photos".format( self.__storePath, person["name"],
			person["_id"] )
		if not os.path.isdir( photosDir ):
			os.makedirs( photosDir )
		self.__savePhotos( person, photosDir )
		# Index
		indexDir = "{0}/index".format( self.__storePath )
		if not os.path.isdir( indexDir ):
			os.makedirs( indexDir )
		self.__indexPerson( person, indexDir )
	
	def __getPingTime( self, person ):
		pingTimeString = person["ping_time"].split( ".", 1)[0]
		pingTime = datetime.datetime.strptime( pingTimeString,
			"%Y-%m-%dT%H:%M:%S" )
		return pingTime

	def __updatePerson( self, person ):
		id_ = person["_id"]
		name = person["name"]
		if id_ in self.__people:
			savedPingTime = self.__getPingTime( self.__people[id_] )
			newPingTime = self.__getPingTime( person )
			if newPingTime > savedPingTime:
				self.__printMsg( "Updating {0} in the store:".format( name ) )
				self.__savePerson( person )
				self.__people[id_] = person
				self.__printMsg( "{0} updated.".format( name ) )
			else:
				msg = "{0} is up to date in the store.".format( name )
				self.__printMsg( msg )
		else:
			self.__printMsg( "Adding {0} to the store:".format( name ) )
			self.__savePerson( person )
			self.__people[id_] = person
			self.__printMsg( "{0} added.".format( name ) )
				
	def requestRecommendations( self ):
		self.__printMsg( "Requesting recommendations ..." )
		response = requests.get( "{0}/user/recs".format( HOST ),
			headers=self.__headers )
		if not self.__validResponse( response ):
			return
		recommendations = response.json()["results"]
		self.__printMsg( "{0} recommendations:".format(
			len( recommendations ) ) )
		for person in recommendations:
			if self.__cancelling:
				self.__cancelling = False
				return
			self.__updatePerson( person )
		self.__printMsg( "{0} total people.".format(
			len( self.__people ) ) )

	def updateStore( self ):
		if not os.path.isdir( self.__storePath ):
			self.__printMsg( "Cannot update store: Store doesn't exist" )
			return
		for id_, person in self.__people.items():
			if self.__cancelling:
				self.__cancelling = False
				return
			self.__updatePerson( person )
			
	def __updateMatchedPerson( self, person, matchDir ):
		self.__printMsg( "Updating match with {0} ...".format(
			person["name"] ) )
		self.__updatePerson( person )
		self.__matchedPeople[person["_id"]] = person
		self.__indexPerson( person, matchDir )
		self.__printMsg( "{0}'s match updated.".format(
			person["name"] ) )

	def requestUpdates( self ):
		data = json.dumps( {"last_activity_date": ""} )
		response = requests.post( "{0}/updates".format( HOST ),
			headers=self.__headers, data=data )
		if not self.__validResponse( response ):
			return
		responseDict = response.json()
		self.__matches = responseDict["matches"]
		self.__printMsg( "Updating matches ..." )
		matchDir = "{0}/matches".format( self.__storePath )
		if not os.path.isdir( matchDir ):
			os.makedirs( matchDir )
		for match in self.__matches:
			if self.__cancelling:
				self.__cancelling = False
				return
			self.__updateMatchedPerson( match["person"], matchDir )
		self.__printMsg( "{0} matches updated.".format(
			len( self.__matches ) ) )
		self.__blocks = responseDict["blocks"]

	def like( self, id_ ):
		if id_ not in self.__people:
			self.__printMsg( "Don't know about her/him" )
			return
		person = self.__people[id_]
		self.__printMsg( "Liking {0} ...".format( person["name"] ) )
		requestMsg = "{0}/like/{1}".format( HOST, id_ )
		response = requests.get( requestMsg, headers=self.__headers )
		if not self.__validResponse( response ):
			return
		responseDict = response.json()
		if responseDict["match"]:
			msg = "You've got a MATCH with {0}!".format( person["name"] )
			self.__printMsg( msg )
		self.__remainingLikes = responseDict["likes_remaining"]
		self.__printMsg( "{0} likes remaining.".format(
			self.__remainingLikes ) )
