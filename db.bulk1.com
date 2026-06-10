$TTL 86400
@   IN  SOA ns1.bulk1.com. admin.bulk1.com. (
            2026060901 ; Serial
            3600       ; Refresh
            1800       ; Retry
            604800     ; Expire
            86400 )    ; Minimum TTL

@   IN  NS  ns1.bulk1.com.
@   IN  A   192.168.10.10
www IN  A   192.168.10.10
