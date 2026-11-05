// Test-only interposer: restrict IPv4/IPv6 wildcard listeners to loopback.
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dlfcn.h>
#include <netinet/in.h>
#include <string.h>
#include <sys/socket.h>
int bind(int fd, const struct sockaddr *addr, socklen_t len) {
    static int (*real_bind)(int, const struct sockaddr *, socklen_t);
    if (!real_bind) real_bind = dlsym(RTLD_NEXT, "bind");
    if (addr && addr->sa_family == AF_INET && len >= sizeof(struct sockaddr_in)) {
        struct sockaddr_in tmp; memcpy(&tmp, addr, sizeof(tmp));
        if (tmp.sin_addr.s_addr == htonl(INADDR_ANY)) tmp.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        return real_bind(fd, (const struct sockaddr *)&tmp, sizeof(tmp));
    }
    if (addr && addr->sa_family == AF_INET6 && len >= sizeof(struct sockaddr_in6)) {
        struct sockaddr_in6 tmp; memcpy(&tmp, addr, sizeof(tmp));
        if (IN6_IS_ADDR_UNSPECIFIED(&tmp.sin6_addr)) tmp.sin6_addr = in6addr_loopback;
        return real_bind(fd, (const struct sockaddr *)&tmp, sizeof(tmp));
    }
    return real_bind(fd, addr, len);
}
