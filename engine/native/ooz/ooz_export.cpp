// Reliquary's bridge to ooz: the open-source Kraken decoder in kraken.cpp (GPL-3.0, (C) 2016 Powzix,
// https://github.com/powzix/ooz), exported under Oodle's OodleLZ_Decompress signature so the
// Forge parser can load ooz.dll exactly as it would load oo2core_*_win64.dll.
#include "stdafx.h"

int Kraken_Decompress(const byte *src, size_t src_len, byte *dst, size_t dst_len);

// ooz may write a few bytes past the end of the output, so it decodes into a padded buffer.
static const size_t kSafeSpace = 64;

extern "C" __declspec(dllexport) int64 OodleLZ_Decompress(
    const void *src, int64 src_len, void *dst, int64 dst_len,
    int32 fuzz, int32 check_crc, int32 verbosity, void *dst_base, int64 dst_base_size,
    void *callback, void *callback_context, void *scratch, size_t scratch_size, int32 thread_phase) {
  if (src_len < 0 || dst_len < 0) return 0;
  // its bit readers also fetch a few bytes past the end of the input: give them zeros to read
  byte *input = (byte *)calloc((size_t)src_len + kSafeSpace, 1);
  byte *padded = (byte *)malloc((size_t)dst_len + kSafeSpace);
  int decoded = -1;
  if (input && padded) {
    memcpy(input, src, (size_t)src_len);
    decoded = Kraken_Decompress(input, (size_t)src_len, padded, (size_t)dst_len);
    if (decoded == dst_len) memcpy(dst, padded, (size_t)dst_len);
  }
  free(input);
  free(padded);
  return decoded < 0 ? 0 : decoded;
}

// LZNA and Bitknit live in ooz sources that carry no license, and Siege archives don't use them:
// these stand-ins make such blocks fail cleanly instead.
struct LznaState;
struct BitknitState;
int LZNA_DecodeQuantum(byte *, byte *, byte *, const byte *, const byte *, LznaState *) { return -1; }
void LZNA_InitLookup(LznaState *) {}
void BitknitState_Init(BitknitState *) {}
size_t Bitknit_Decode(const byte *, const byte *, byte *, byte *, byte *, BitknitState *) { return 0; }
