#! /usr/bin/python3
#
# RudiaPrody.py -- listen for incoming udp packets and forward them bidirectionally.
# 2020 (C) juergen@fabmail.org
# Distribute under GPLv2 or ask.
#
# References (and thanks to):
# * https://wiki.fablab-nuernberg.de/w/Diskussion:Nova_35
# * https://github.com/kkaempf/LibLaserCut/tree/thunderlaser/src/com/t_oster/liblasercut/drivers/ruida
#
# This listens at port 50200 and 40200 udp.

# A UDP stream ends when there is a pause for more than 10 seconds, or when an
#      END command is seen in the stream.
#      Finish e7 00                            eb e7 00
#      Work_Interval 01 06 20 348.0mm 348.0mm  da 01 06 20 00 00 00 02 5c 00 00 00 02 5c
#      Run                                     d7
#
# We define a logical UDP "Stream" to have pauses shorter than 10 sec between packets.
#
# - Each UDP packet is acknowledged with a single byte response packet:
#   0xc6 if all is well, 0x46 if checksum error.
# - IF a UDP Stream already exists, additional incoming packets are NaK'ed with 0x46
#
# Packets are alway sent from port 50200 and are always received by port 40200.


import os, sys, time, select
from socket import *

if sys.version_info.major < 3:
  print("Need python3 for "+sys.argv[0])
  sys.exit(1)

if len(sys.argv) < 3:
  print("Usage: %s RUIDA_IP_ADDR" % sys.argv[0])
  sys.exit(1)

class RuidaProxyServer():
  BUSY_TIMEOUT = 10000    # ends a UDP Stream.
  INADDR_ANY_DOTTED = '0.0.0.0'  # bind to all interfaces.
  SOURCE_PORT = 40200     # used by rdworks in Windows
  DEST_PORT   = 50200     # Ruida Board
  verbose = True          # babble while working
  ACK_BYTE = 0xc6
  NACK_BYTE = 0x46	  # csum error. FIXME: do we kow other error codes?
  CHUNK_SZ = 10000	  # max size per udp packet
  FIN_TOKEN = "\xd7"      # the last packet in a transmission contains this.

  def __init__(self, port=DEST_PORT):
    localport = port

    self.udp_sock_world = socket(AF_INET, SOCK_DGRAM)
    self.udp_sock_world.setsockopt(SOL_SOCKET, socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.udp_sock_world.bind((self.INADDR_ANY_DOTTED, int(DEST_PORT)))

    self.udp_sock_laser = socket(AF_INET, SOCK_DGRAM)
    self.udp_sock_laser.setsockopt(SOL_SOCKET, socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.udp_sock_laser.bind((self.INADDR_ANY_DOTTED, int(SO_REUSEADDR)))

  def find_end_token(data):
    if FIN_TOKEN in data:
      return True
    False


proxy = RuidaProxyServer()
last_pkg_tstamp = 0     # seconds since epoch
last_sender_addr = 0    # the one remote machine, that "currently" sends.
stream_busy = False     # True until we find_end_token()


while True:
  ending = False
  inputs = [proxy.udp_sock_laser, proxy.udp_sock_world]

  try:
    inputready,outputready,exceptready = select.select(inputs, [], [])
  except select.error as e:
    break
  except socket.error as e:
    break


  if proxy.udp_sock_world in inputready:
    now = time.time()
    data, sender_addr = proxy.udp_sock_world.recvfrom(proxy.CHUNK_SZ)
    if (now - last_pkg_tstamp < BUSY_TIMEOUT):
        # we forward packets that come from the same sender than before
        # we reject packets from different sender.
    else:
        # timeout reached. 
        # we accept any other sender as new source.
        # if the stream is still busy, we send an artificial fin token to the laser, then we start forwarding.
        if stream_busy:


  if proxy.tcp_sock in inputready:
    conn, sender_addr = proxy.tcp_sock.accept()
    if proxy.busy:
      try:
        conn.send(proxy.NACK_BYTE)
      except:
        pass
      try:
        conn.shutdown(socket.SHUT_RDWR)
      except:
        pass
    else:
      # not yet busy
      proxy.tcp_conn = conn
      proxy.busy = True
      proxy.output = ( 0, sender_addr, "out_"+str(time.time())+".rd")
      proxy.output[0] = open(proxy.output[2], "w")
  # tcp_sock

  if proxy.busy and proxy.tcp_conn is not None and proxy.tcp_conn.fileno() in inputready:
    data = proxy.udp_sock.recv(proxy.CHUNK_SZ)
    proxy.output[0].write(data)
    proxy.tcp_conn.send(proxy.ACK_BYTE)
    ending = proxy.find_end_token(data)
  # tcp_conn

  if proxy.udp_sock in inputready:
    data, sender_addr = proxy.udp_sock.recvfrom(proxy.CHUNK_SZ)
    if proxy.busy:
      if proxy.output[1] == sender_addr:
        proxy.output[0].write(data)
        proxy.udp_sock.sendto(sender_addr, proxy.ACK_BYTE)
        ending = proxy.find_end_token(data)
      else:
        try:
          proxy.udp_sock.sendto(sender_addr, proxy.NACK_BYTE)
        except:
          pass
    else:
      # not yet busy
      proxy.busy = True
      proxy.output = ( 0, sender_addr, "out_"+str(time.time())+".rd")
      proxy.output[0] = open(proxy.output[2], "w")
      proxy.output[0].write(data)
      proxy.udp_sock.sendto(sender_addr, proxy.ACK_BYTE)
      ending = proxy.find_end_token(data)
  # udp_sock

  if ending:
    proxy.output[0].close()
    proxy.output = None
    proxy.busy = False

