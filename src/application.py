import argparse
import socket
import time
from collections import deque
from datetime import datetime
from DRTP import DRTP


def server_program(ip, port, discard_seq):
    # creete a socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # bind the socket to the provided IP and port
    server_socket.bind((ip, port))
    print(f'Server is ready')

    drtp = DRTP()  # initialize DRTP object

    # some variables
    data_received = 0
    start_time = time.time()  # starting time to calculate throughput
    connection_established = False  # for to determine befor connection and after connection fases.
    expected_seq_num = 1  # for to use when we orginize window size
    discarded = False  # for to discard a packet just for once.

    # main loop
    while True:
        # recieve a packet from the client
        packet, addr = server_socket.recvfrom(1000)
        # parse the packet using the drtp object
        seq_num, ack_num, syn, ack, fin, data = drtp.parse_packet(packet)

        # If syn flag is set and connection is not established yet, acknowledge the SYN packet
        if syn and not connection_established:
            print('SYN packet is received')
            # Send SYN-ACK packet
            syn_ack_packet = drtp.create_packet(b'', syn=True, ack=True)
            server_socket.sendto(syn_ack_packet, addr)
            print('SYN-ACK packet is sent')
        # if ack flag is set and connection is not established yet
        elif ack and not connection_established:
            print('ACK packet is received')
            print('Connection established')
            connection_established = True
            start_time = time.time()
        # End of Three-way handshake

        # Connection is established
        elif connection_established:

            # check if the packet is a FIN packet
            if fin:
                print('....\n')
                print('FIN packet is received')
                # Send FIN-ACK packet
                drtp.send_ack(server_socket, addr, fin=True)
                print('FIN ACK packet is sent\n')
                break
            # data transfer fase.
            else:
                # discard packet just for once
                if seq_num == discard_seq and not discarded:
                    print('Discarding packet with seq = {}'.format(seq_num))
                    time.sleep(0.6)  # delay longer than the client's timeout period
                    discarded = True  # Mark as discarded
                    continue
                # check if the packet is the correct packet
                elif seq_num == expected_seq_num:
                    print('{} -- packet {} is received'.format(datetime.now().time(), seq_num))
                    drtp.send_ack(server_socket, addr) # send ack for received (correct) packet
                    print('{} -- sending ack for the received {}'.format(datetime.now().time(), seq_num))
                    # write the data to a file named 'received_file
                    with open('received_file', 'ab') as f:
                        if data:
                            f.write(data)
                            data_received += len(data) # length of the data for to calculate throughput
                    expected_seq_num += 1
                # if the packet has not expected seq_num, mark as out of order
                else:
                    print('Out of order packet {} received, expected {}'.format(seq_num, expected_seq_num))
                    # no operation for out of order packets
    # close the socket (connection)
    server_socket.close()

    end_time = time.time()  # to calculate throughput
    elapsed_time = end_time - start_time
    throughput = "{:.2f}".format(data_received / elapsed_time / 125000)  # Convert to Mbps
    print('The throughput is {} Mbps'.format(throughput))
    print('Connection Closes')


def send_file_gbn(socket, host, port, filename, window_size):
    # some variables for to organize the sliding window and retransmitting the packets in correct order
    base = 1
    next_seq_num = 1
    sliding_window = {}
    acked_packets = set()

    # create an DRTP object
    drtp = DRTP()

    ''' For further developments
    This part could be more effective if i could manage to read 
    relevant part of the data instead of reading whole data.
    Due to lack of experience in python i couldnt manage it.'''

    # read the data in binary mode.
    with open(filename, 'rb') as f:
        data = f.read()

    number_of_packets = (len(data) + 994 - 1) // 994  # needed for to organize sliding window

    while base < number_of_packets:
        # send number of packets which is defined by -w (window-size)
        while next_seq_num < base + window_size and next_seq_num <= number_of_packets:
            # take correct 994 bytes of data
            start = (next_seq_num - 1) * 994
            end = min(start + 994, len(data))
            # set the correct 994 bytes of data in to a packet.
            packet = drtp.create_packet(data[start:end])
            socket.sendto(packet, (host, port))  # send the packet
            sliding_window[next_seq_num] = packet  # set the packet into the sliding window dictionary
            print('{} -- packet with seq = {} is sent, sliding window = {}'.format(datetime.now().time(), next_seq_num, list(sliding_window)))
            next_seq_num += 1  # update the next expected seq_num

        # after sending so many packet as window-size, wait for ack for first packet in flight.
        try:
            # receive packet
            ack_packet, _ = socket.recvfrom(1000)
            seq_num, ack_num, syn, ack, fin, _ = drtp.parse_packet(ack_packet)  # open the packet received

            # if packet is an ack
            if ack:
                print('{} -- Ack for packet = {} is received'.format(datetime.now().time(), ack_num))  # send a message about received ack
                acked_packets.add(ack_num)  # set the ack_num of the ack packet into a set
                base = min(sliding_window.keys())  # update the base to continue packet sending in correct order
                # update the base and acked_packets for sliding the window correctly
                while base in acked_packets:
                    del sliding_window[ack_num]
                    base += 1
        #  if client doesnt take an ack in period of timeout
        except TimeoutError:
            print(f'{datetime.now().time()} -- Timeout occurred, resending packets from seq = {base}')
            # retransmit packets which is discarded/lost and the following packets within the current window size
            for seq_num in sliding_window.keys():
                if seq_num not in acked_packets:
                    # Retransmit the packet and give feed back
                    socket.sendto(sliding_window[seq_num], (host, port))
                    print(f'{datetime.now().time()} -- Retransmitting packet with seq = {seq_num}')

    # end of the data transfer. data is sent completely
    print("\nData transfer is finished\n")


def client_program(host, port, filename, window_size):
    # create a socket (connection)
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(0.5)  # set timeout to 500ms

    # create a drtp object which is going to be used for to pack the data, send ack and parse each packet.
    drtp = DRTP()
    # to determine the before and after connection sections
    connection_established = False
    # Connection Establish Phase with Three-way handshake
    print("Connection Establish Phase:\n")

    # Send a SYN packet. Three-way handshake starts here.
    syn_packet = drtp.create_packet(b'', syn=True)
    client_socket.sendto(syn_packet, (host, port))
    print('SYN packet is sent')

    # Wait for SYN-ACK packet
    while not connection_established:
        try:
            packet, addr = client_socket.recvfrom(1000)
            seq_num, ack_num, syn, ack, fin, data = drtp.parse_packet(packet)

            if syn and ack:
                print('SYN-ACK packet is received')
                connection_established = True
                # Send ACK packet
                drtp.seq_num += 1  # Increase sequence number for the next packet
                ack_packet = drtp.create_packet(b'', ack=True)
                client_socket.sendto(ack_packet, (host, port))
                print('ACK packet is sent\n')
                print("Connection established\n")
                print('\nData transfer:\n')
        # if SYN-ACK not come on time send new one.
        except socket.timeout:
            client_socket.sendto(syn_packet, (host, port))
            print('SYN packet is re-sent')
    # Three-way handshake is done here

    # Send the file by using Go-Back-N
    send_file_gbn(client_socket, host, port, filename, window_size)

    # End the connection with handshake.
    print("Connection Teardown:\n")

    # Send FIN packet
    fin_packet = drtp.create_packet(b'', fin=True)
    client_socket.sendto(fin_packet, (host, port))
    print('FIN packet is sent')

    # Wait for FIN-ACK packet
    while True:
        packet, addr = client_socket.recvfrom(1000)
        seq_num, ack_num, syn, ack, fin, data = drtp.parse_packet(packet)

        if fin and ack:
            print('FIN ACK packet is received')
            break

    # Close the socket (connection)
    print("\nConnection Closes\n")
    client_socket.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='DRTP File Transfer Application')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-s', '--server', action='store_true', help='Run as server')
    group.add_argument('-c', '--client', action='store_true', help='Run as client')
    parser.add_argument('-p', '--port', type=int, required=True, help='Port number')
    parser.add_argument('-i', '--ip', required=True, help='IP address of the server')
    parser.add_argument('-f', '--file', help='File to send')
    parser.add_argument('-w', '--window', type=int, default=3, help='Sliding window size')
    parser.add_argument('-d', '--discard', type=int, default=float('inf'), help='Sequence number of packet to discard')

    args = parser.parse_args()

    if args.server:
        server_program(args.ip, args.port, args.discard)
    elif args.client:
        if args.file is None:
            print('Please specify a file to send')
        else:
            client_program(args.ip, args.port, args.file, args.window)