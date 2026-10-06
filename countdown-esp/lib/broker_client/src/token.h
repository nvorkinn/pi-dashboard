#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

#include "ports.h"

namespace countdown {

// RFC 4648 base64url (`-` and `_` for `+` and `/`) without `=` padding.
std::string base64UrlEncode(const uint8_t* data, size_t length);

// The same as Python's secrets.token_urlsafe(nbytes): `nbytes` random bytes, base64url-encoded.
std::string tokenUrlsafe(Random& random, size_t nbytes = 24);

}  // namespace countdown
