import struct

class DRTP:
    def __init__(self):
        self.seq_num = 1  # id for packets with data
        self.ack_num = 1  # id for ack packets

    # create a packet with header and data.
    # 6 bytes Header includes ack_num, seq_num and flags.
    # 994 bytes data
    def create_packet(self, data, seq_num=None, ack_num=None, syn=False, ack=False, fin=False, rst=False):
        # create the flags from input parameters syn, ack, fin, rst and order them
        flags = (syn << 3) | (ack << 2) | (fin << 1) | rst
        # create the header with sequence number, acknowledgement number, and lags
        header = struct.pack('!HHH', self.seq_num, self.ack_num, flags)
        self.seq_num += 1  # Increase the seq_num for each packet creation
        packet = header + data
        return packet

    # open the packet.
    def parse_packet(self, packet):
        # take the header and data out of the packet
        header = packet[:6]
        data = packet[6:]
        # unpack header into sequence number, acknowledgement number and flags
        seq_num, ack_num, flags = struct.unpack('!HHH', header)
        # Extract each flags from packed flags
        syn = bool(flags & 0b1000)
        ack = bool(flags & 0b0100)
        fin = bool(flags & 0b0010)
        rst = bool(flags & 0b0001)

        # return the values extracted from packet
        return seq_num, ack_num, syn, ack, fin, data

    # Create an ack packet and send it
    def send_ack(self, socket, addr, seq_num=None, ack_num=None, fin=False, rst=False):
        # create an ack packet with optional fin and rst flags ( ack = True)
        ack_packet = self.create_packet(b'', ack=True, fin=fin, rst=rst)
        # send the ack packet to the specified adress
        socket.sendto(ack_packet, addr)
        self.ack_num += 1 # increase the ack_num for next packet
