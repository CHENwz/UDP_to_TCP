from socket import *
import pickle
import time
import threading
import sys


#数据包，id为数据包编号，与服务端ACK一个意思
class Packet:
    def __init__(self, packet_id, data):
        super(Packet, self).__init__()
        self.packet_id = packet_id
        self.data = data


#这是第一次发送给服务器信息数据包，包括所传输文件名，服务器根据这个创建新文件
class Connect_packet():
    def __init__(self, packet_id, file_name, send_or_get):
        super(Connect_packet, self).__init__()
        self.packet_id = packet_id
        self.file_name = file_name
        self.send_or_get = send_or_get


#第一个参数为服务器期望的ack，即包的id，是缓存区的第一位，第二个为服务器缓存区收到的最大id的数据包，
#第三个参数为服务器的最大id之后空余的缓存区数量
class Confirm_packet():  
    def __init__(self, first_want_ack, port):
        super(Confirm_packet, self).__init__()
        self.first_want_ack = first_want_ack
        self.port = port
        
        






#发送文件给指定IP和端口
def send_file(file_name, Service_ip):
    #尝试打开文件，确认文件是存在的
    try:
        f = open(file_name, 'rb')
    except IOError: #报错
        print("Error: can't find the file " + file_name)
    else:  #文件存在，进行发送

        #服务器IP及端口，固定20000，这个只用来传第一个connectpacket
        ADDR = (Service_ip, 20000)

        #发送数据包的socket
        udp_Send_Sock = socket(AF_INET, SOCK_DGRAM)

        #接受ACK确认包的socket,并与本机地址绑定
        udp_Recv_Sock = socket(AF_INET, SOCK_DGRAM)
        udp_Recv_Sock.bind(('127.0.0.1',30000))  



        #第一次发送包，发送文件名
        connect_packet = pickle.dumps(Connect_packet(-100,file_name, "send"))
        udp_Send_Sock.sendto(connect_packet, ADDR)

        #接收服务器的确认包，确认已建好文件，这个丢包就没办法了
        confirm_pck_, addr = udp_Recv_Sock.recvfrom(1024) 
        confirm_packet = pickle.loads(confirm_pck_)

        #根据返回的确认包里面的port重新写ADDR
        ADDR = (Service_ip, confirm_packet.port)

        #缓存区数据，first_send_id为已发送但还没确认的第一个数据包id，
        #last_send_id为已发送但还没确认的最后一个数据包id，所以last_send_id+1就是准备发送的包
        #cache_datas为缓存区，最大为10,保存已经发送但还没确认的数据包
        first_send_id = 1 #first 和 last都从1开始，last这里设为0是因为在循环里面会+1
        last_send_id = 0
        cache_datas = {}
        variable_change = threading.Lock()



        #发送一个数据包之后，开一个子线程，调用这个函数，该函数1s之后检查收到ACK没有
        #（就判断缓存区里这个数据包还在不在，在的话证明还没收到，继续发送，否则跳出）、
        def time_out_check(packet_id):
            nonlocal variable_change
            nonlocal cache_datas
            nonlocal ADDR
            nonlocal udp_Send_Sock
            while True:
                time.sleep(1) #预计接收时间1s
                variable_change.acquire()
                if packet_id in cache_datas: #超时，再发一次该数据包，然后继续等待1s
                    udp_Send_Sock.sendto(pickle.dumps(cache_datas[packet_id]), ADDR)
                    variable_change.release()
                else:  #ACK已经接收到，结束这个函数/子线程
                    variable_change.release()
                    break

        #循环接收服务端发来的确认数据包，分析first_want_ack和缓存区数据，更新客户端的数据，
        #如果发来的first_want_ack是需要重传的那个数据包（即这个ACK下标数据包在缓存区），
        #删除first_want_ack前的数据，重发cache_datas[ACK],修改first_send_id等数据
        def recv_confirm_packet():
            nonlocal cache_datas
            nonlocal variable_change
            nonlocal ADDR
            nonlocal first_send_id
            nonlocal last_send_id
            nonlocal udp_Send_Sock
            nonlocal udp_Recv_Sock
            nonlocal last_byte_ack
            nonlocal c_wnd
            nonlocal dup_ack_count
            nonlocal slow_start
            nonlocal fast_recovery
            nonlocal congestion_avoidance
            nonlocal ss_thresh
            while True:
                datas, addr = udp_Recv_Sock.recvfrom(1024)
                confirm_packet = pickle.loads(datas)
                variable_change.acquire()
                if slow_start == 1:#慢启动
                    if confirm_packet.first_want_ack > last_byte_ack:
                        last_byte_ack = confirm_packet.first_want_ack 
                        dup_ack_count = 0
                        c_wnd *= 2
                        if c_wnd >= ss_thresh:#结束慢启动
                            c_wnd += 1
                            congestion_avoidance = 1
                            slow_start = 0
                    elif confirm_packet.first_want_ack == last_byte_ack:
                        dup_ack_count += 1#重复ack+1
                        if dup_ack_count == 3:#准备启动快恢复
                            ss_thresh = c_wnd // 2
                            c_wnd = ss_thresh + 3
                            slow_start = 0
                            fast_recovery = 1
                elif congestion_avoidance == 1:#启动拥塞避免算法
                    if confirm_packet.first_want_ack > last_byte_ack:#加速增
                        last_byte_ack = confirm_packet.first_want_ack 
                        c_wnd += 1
                        dup_ack_count = 0
                    elif confirm_packet.first_want_ack == last_byte_ack:
                        dup_ack_count += 1
                        if dup_ack_count == 3:#准备启动快恢复
                            fast_recovery = 1
                            congestion_avoidance = 0
                            ss_thresh = c_wnd // 2
                            c_wnd = ss_thresh + 3
                elif fast_recovery == 1:
                    if confirm_packet.first_want_ack > last_byte_ack:
                        last_byte_ack = confirm_packet.first_want_ack
                        c_wnd = ss_thresh
                        dup_ack_count = 0
                        fast_recovery = 0
                        congestion_avoidance = 1
                    elif confirm_packet.first_want_ack == last_byte_ack:
                        c_wnd += 1
                print("c_wnd=" + str(c_wnd) + " ss_thresh=" + str(ss_thresh) + " slow_start=" + str(slow_start))
                print("ACK: " + str(confirm_packet.first_want_ack))
                if confirm_packet.first_want_ack > first_send_id and confirm_packet.first_want_ack <= last_send_id: #前面的包已经确认,但仍然有丢包
                    num = confirm_packet.first_want_ack - first_send_id
                    for x in range(0,num):
                        del cache_datas[first_send_id]
                        first_send_id = first_send_id + 1
                    udp_Send_Sock.sendto(pickle.dumps(cache_datas[confirm_packet.first_want_ack]), ADDR)

                elif confirm_packet.first_want_ack < first_send_id: #ack来得慢了一点,无影响
                    pass
                elif confirm_packet.first_want_ack == first_send_id:  #丢包，传输
                    udp_Send_Sock.sendto(pickle.dumps(cache_datas[first_send_id]), ADDR)

                else: #confirm_packet.first_want_ack > last_send_id,说明全部传输完成，清空
                    cache_datas.clear()
                    first_send_id = confirm_packet.first_want_ack + 1
                variable_change.release()
                

        ss_thresh = 100
        c_wnd = 1
        dup_ack_count = 0
        last_byte_ack = -1
        slow_start = 1
        congestion_avoidance = 0
        fast_recovery = 0
        #创建一个子线程，循环接受服务端发来的确认数据
        recv_pck_thread = threading.Thread(target=recv_confirm_packet)
        recv_pck_thread.daemon = True
        recv_pck_thread.start()
         
        #判断是否结束传输
        need_trans = True
        finish_read_file = False
        #发送文件直到该文件已发送完并缓存区已清空
        while need_trans:
            time.sleep(0.5)
            variable_change.acquire()
            #已发送的和empty_cache_num加起来不能超过10，因为接收端的缓存区也为10
            empty_cache_num = c_wnd - len(cache_datas) 
            for x in range(0, empty_cache_num):
                data = f.read(8192) #一个包的数据1024
                #数据读完了
                if not data:
                    if finish_read_file == False: #发送id为-1的证明已经传完
                        udp_Send_Sock.sendto(pickle.dumps(Packet(-1, data)), ADDR)
                        finish_read_file = True
                    if len(cache_datas) == 0: ##证明已经完成文件传输并全部确认
                        print("finish")
                        f.close()
                        udp_Send_Sock.close()
                        udp_Recv_Sock.close()
                        need_trans = False #结束循环（程序）
                    break
                last_send_id = last_send_id + 1
                cache_datas[last_send_id] = Packet(last_send_id, data)
                #if last_send_id == 10:
                #   pass
                #else:
                #    udp_Send_Sock.sendto(pickle.dumps(cache_datas[last_send_id]), ADDR)
                udp_Send_Sock.sendto(pickle.dumps(cache_datas[last_send_id]), ADDR)
                t = threading.Thread(target=time_out_check, args=[last_send_id])
                t.daemon = True
                t.start()
                
            variable_change.release()
    
    #参数为文件名，服务端地址
def recive_file(file_name, Service_ip):
    ADDR = (Service_ip, 20000) 

    #发送给服务器想下载的文件，服务器的首次接收信息均用20000端口
    udp_Send_Sock = socket(AF_INET, SOCK_DGRAM)
    connect_packet = pickle.dumps(Connect_packet(-100,file_name, "get"))
    udp_Send_Sock.sendto(connect_packet, ADDR)

    #接收服务器数据包的socket,并与本机地址绑定，40000为客户端接收数据的端口
    udp_Recv_Sock = socket(AF_INET, SOCK_DGRAM)
    udp_Recv_Sock.bind(("127.0.0.1",40000)) 


    #接收第一个确认包，这个包包含了服务器是否有这个文件，如果有还分配了一个端口
    datas, addr = udp_Recv_Sock.recvfrom(1024)
    confirm_packet = pickle.loads(datas)

    if confirm_packet.first_want_ack == -2:
        print("the service don't have the file " + file_name)
        sys.exit()
    else:
        ADDR = (Service_ip, confirm_packet.port)
        f = open(file_name, 'wb')

    #cache_datas为缓存区,
    cache_datas = {}
    #想要的数据包id，初始为1
    first_want_ack = 1;
    #判断是否客户端是否已经发了最后一个
    have_recv_final = False
    #不断接收文件直到缓存区为空并且接收到id=-1
    while True:
        datas, addr = udp_Recv_Sock.recvfrom(8192+100)
        packet = pickle.loads(datas)
        if packet.packet_id == -1: #证明对面已经把所有数据包传了一遍，但可能存在丢包
            have_recv_final = True
            if len(cache_datas) == 0:
                print("finish")
                f.close()
                break
        elif packet.packet_id == first_want_ack: #接收到了缓存区需要的第一个数据
            f.write(packet.data)
            print("first_want_ack: " + str(first_want_ack))
            time.sleep(0.5)
            first_want_ack += 1
            while first_want_ack in cache_datas:
                f.write(cache_datas[first_want_ack].data)
                del cache_datas[first_want_ack]
                first_want_ack += 1
            if have_recv_final and len(cache_datas) == 0:
                print("finish!")
                f.close()
                break
            udp_Send_Sock.sendto(pickle.dumps(Confirm_packet(first_want_ack,40000)), ADDR)
        elif packet.packet_id < first_want_ack: #丢弃掉，不是自己想要的
            #udp_Send_Sock.sendto(pickle.dumps(confirm_packet(first_want_ack,my_port)), ADDR)
            pass
        else:  #packet.packet_id > first_want_ack
            if packet.packet_id in cache_datas:
                pass
            else:
                cache_datas[packet.packet_id] = packet
            udp_Send_Sock.sendto(pickle.dumps(Confirm_packet(first_want_ack,40000)), ADDR)



if __name__ == "__main__":  #客户端的30000端口用来上传时接收确认包，40000端口是用来下载时接收数据包
    text = input("input the command('q' to exit): ")
    if text == "q":
        sys.exit()
    info = text.split()
    if len(info) != 4:
        print("can't find the command")
    elif info[0] == "LFTP" and info[1] == "lsend":
        send_file(info[3], info[2])
    elif info[0] == "LFTP" and info[1] == "lget":
        recive_file(info[3], info[2])
    else:
        print("can't find the command")
