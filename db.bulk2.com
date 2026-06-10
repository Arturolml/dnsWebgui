$TTL 86400
@   IN  SOA ns1.bulk2.com. admin.bulk2.com. (
            2026060901 ; Serial
            3600       ; Refresh
            1800       ; Retry
            604800     ; Expire
            86400 )    ; Minimum TTL

@   IN  NS  ns1.bulk2.com.
@   IN  A   192.168.20.20
www IN  A   192.168.20.20
