"""AES-256-CBC 加密，按 FIPS-197 独立实现，用来构造加密样本。

被测的 cli/keyscan/aes.py 只做解密；这里的 S 盒由有限域求逆与仿射变换现场算出，不与它共用任何表。
"""

__all__ = ["aes256_cbc_encrypt"]


def _double(value: int) -> int:
    """GF(2^8) 上乘以 x，模多项式 x^8 + x^4 + x^3 + x + 1。"""
    value <<= 1
    return value ^ 0x11B if value & 0x100 else value


def _multiply(left: int, right: int) -> int:
    product = 0
    while right:
        if right & 1:
            product ^= left
        left, right = _double(left), right >> 1
    return product


def _substitution_box() -> list[int]:
    """S 盒: 先取乘法逆元 (0 映射到 0)，再做仿射变换。"""
    box = []
    for value in range(256):
        inverse = next((candidate for candidate in range(1, 256) if _multiply(value, candidate) == 1), 0)
        mixed = inverse
        for shift in range(1, 5):
            mixed ^= ((inverse << shift) | (inverse >> (8 - shift))) & 0xFF
        box.append(mixed ^ 0x63)
    return box


_SBOX = _substitution_box()
_TWICE = [_double(value) for value in range(256)]
_THRICE = [_double(value) ^ value for value in range(256)]


def _round_keys(key: bytes) -> list[bytes]:
    """256 位密钥扩展为 15 个轮密钥。"""
    words = [list(key[index:index + 4]) for index in range(0, 32, 4)]
    constant = 1
    for index in range(8, 60):
        word = list(words[index - 1])
        if index % 8 == 0:
            word = [_SBOX[byte] for byte in word[1:] + word[:1]]
            word[0] ^= constant
            constant = _double(constant)
        elif index % 8 == 4:
            word = [_SBOX[byte] for byte in word]
        words.append([left ^ right for left, right in zip(words[index - 8], word, strict=True)])
    return [bytes(byte for word in words[start:start + 4] for byte in word) for start in range(0, 60, 4)]


def _encrypt_block(block: bytes, keys: list[bytes]) -> bytes:
    state = [byte ^ key for byte, key in zip(block, keys[0], strict=True)]
    for number in range(1, 15):
        # 字节代换与行移位: 状态按列存放，第 row 行左移 row 列
        state = [_SBOX[state[(column + row) % 4 * 4 + row]] for column in range(4) for row in range(4)]
        if number != 14:
            mixed = []
            for column in range(0, 16, 4):
                a, b, c, d = state[column:column + 4]
                mixed += [_TWICE[a] ^ _THRICE[b] ^ c ^ d, a ^ _TWICE[b] ^ _THRICE[c] ^ d, a ^ b ^ _TWICE[c] ^ _THRICE[d], _THRICE[a] ^ b ^ c ^ _TWICE[d]]
            state = mixed
        state = [byte ^ key for byte, key in zip(state, keys[number], strict=True)]
    return bytes(state)


def aes256_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    """以 32 字节 key 与 16 字节 iv 加密；plaintext 长度须为 16 的倍数，不做填充。"""
    if len(key) != 32 or len(iv) != 16 or len(plaintext) % 16:
        raise ValueError("key 须为 32 字节，iv 为 16 字节，明文长度为 16 的倍数")
    keys = _round_keys(key)
    output = bytearray()
    previous = iv
    for start in range(0, len(plaintext), 16):
        previous = _encrypt_block(bytes(left ^ right for left, right in zip(plaintext[start:start + 16], previous, strict=True)), keys)
        output += previous
    return bytes(output)
