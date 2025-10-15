# dduckdns

**dduckdns** is a client for the [Duck DNS](https://www.duckdns.org/) dynamic DNS service.
dduckdns is implemented as a single-file Python script with no dependencies besides the Python standard library.

## Configuration

dduckdns is configured using a TOML file.

```toml
# What command to run to get the Duck DNS token.
# This is intended to access your password manager.
token_command = ["pass", "show", "duckdns"]
# There is no setting for a literal token,
# but you can use a command like this:
# token_command = ["cat", "/home/user/.config/dduckdns/token"]

# Set the IPv4 and the IPv6 for foo.duckdns.org.
[domains.foo]
ip = "1.1.1.1"
ipv6 = "2606:4700:4700::1111"

# If no IPv4 is specified,
# Duck DNS assigns the IPv4 address of the client to the domain.
# It does not do this for IPv6.
# You can specify the IPv6 address explicity
# or set it to `auto` to get the address from https://ipv6.icanhazip.com/.
[domains.bar]
# `ip` is determined by Duck DNS.
ipv6 = "auto"
```

## License

MIT.
