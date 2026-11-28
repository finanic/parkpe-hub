/* Local authenticator QR for the operator console.

   Draws an otpauth URI that auth.server._mfa_setup already returns.
   The secret stays in this page. Nothing is sent to a QR host.
*/
(function () {
  const EXP = new Uint8Array(512);
  const LOG = new Uint8Array(256);
  (function initField() {
    let value = 1;
    for (let i = 0; i < 255; i += 1) {
      EXP[i] = value;
      LOG[value] = i;
      value <<= 1;
      if (value & 0x100) value ^= 0x11d;
    }
    for (let i = 255; i < 512; i += 1) EXP[i] = EXP[i - 255];
  })();

  const ALIGN = [
    [],
    [],
    [6, 18],
    [6, 22],
    [6, 26],
    [6, 30],
    [6, 34],
    [6, 22, 38],
    [6, 24, 42],
    [6, 26, 46],
    [6, 28, 50],
    [6, 30, 54],
    [6, 32, 58],
  ];

  // Level M. [ecc per block, group1 blocks, group1 data, group2 blocks, group2 data]
  const LEVEL_M = {
    1: [10, 1, 16, 0, 0],
    2: [16, 1, 28, 0, 0],
    3: [26, 1, 44, 0, 0],
    4: [18, 2, 32, 0, 0],
    5: [24, 2, 43, 0, 0],
    6: [16, 4, 27, 0, 0],
    7: [18, 4, 31, 0, 0],
    8: [22, 2, 38, 2, 39],
    9: [22, 3, 36, 2, 37],
    10: [26, 4, 43, 1, 44],
    11: [30, 1, 50, 4, 51],
    12: [22, 6, 36, 2, 37],
  };

  function mul(left, right) {
    if (left === 0 || right === 0) return 0;
    return EXP[LOG[left] + LOG[right]];
  }

  function rsDivisor(degree) {
    const result = new Array(degree - 1).fill(0);
    result.push(1);
    let root = 1;
    for (let i = 0; i < degree; i += 1) {
      for (let j = 0; j < result.length; j += 1) {
        result[j] = mul(result[j], root);
        if (j + 1 < result.length) result[j] ^= result[j + 1];
      }
      root = mul(root, 2);
    }
    return result;
  }

  function rsRemainder(data, eccLen) {
    const divisor = rsDivisor(eccLen);
    const result = divisor.map(() => 0);
    data.forEach((byte) => {
      const factor = byte ^ result.shift();
      result.push(0);
      divisor.forEach((coef, index) => {
        result[index] ^= mul(coef, factor);
      });
    });
    return result;
  }

  function pushBits(bits, value, width) {
    for (let i = width - 1; i >= 0; i -= 1) bits.push((value >>> i) & 1);
  }

  function dataCodewords(text, version, capacity) {
    const bytes = Array.from(new TextEncoder().encode(text));
    const bits = [];
    pushBits(bits, 0b0100, 4);
    pushBits(bits, bytes.length, version < 10 ? 8 : 16);
    bytes.forEach((byte) => pushBits(bits, byte, 8));
    const room = capacity * 8;
    if (bits.length > room) return null;
    const terminator = Math.min(4, room - bits.length);
    pushBits(bits, 0, terminator);
    while (bits.length % 8 !== 0) bits.push(0);
    const data = [];
    for (let i = 0; i < bits.length; i += 8) {
      let value = 0;
      for (let j = 0; j < 8; j += 1) value = (value << 1) | bits[i + j];
      data.push(value);
    }
    let pad = 0xec;
    while (data.length < capacity) {
      data.push(pad);
      pad = pad === 0xec ? 0x11 : 0xec;
    }
    return data;
  }

  function interleave(data, spec) {
    const [eccLen, n1, len1, n2, len2] = spec;
    const blocks = [];
    let offset = 0;
    function take(count, length) {
      for (let i = 0; i < count; i += 1) {
        const chunk = data.slice(offset, offset + length);
        offset += length;
        blocks.push({ data: chunk, ecc: rsRemainder(chunk, eccLen) });
      }
    }
    take(n1, len1);
    take(n2, len2);
    const out = [];
    const longest = Math.max(len1, len2);
    for (let i = 0; i < longest; i += 1) {
      blocks.forEach((block) => {
        if (i < block.data.length) out.push(block.data[i]);
      });
    }
    for (let i = 0; i < eccLen; i += 1) blocks.forEach((block) => out.push(block.ecc[i]));
    const bits = [];
    out.forEach((byte) => pushBits(bits, byte, 8));
    return bits;
  }

  function capacityOf(spec) {
    return spec[1] * spec[2] + spec[3] * spec[4];
  }

  function choose(text) {
    const versions = Object.keys(LEVEL_M).map(Number);
    for (let i = 0; i < versions.length; i += 1) {
      const version = versions[i];
      const spec = LEVEL_M[version];
      const data = dataCodewords(text, version, capacityOf(spec));
      if (data) return { version, bits: interleave(data, spec) };
    }
    return null;
  }

  function blank(size) {
    return Array.from({ length: size }, () => Array(size).fill(null));
  }

  function paintFinder(matrix, row, col) {
    for (let r = -1; r <= 7; r += 1) {
      for (let c = -1; c <= 7; c += 1) {
        const y = row + r;
        const x = col + c;
        if (y < 0 || x < 0 || y >= matrix.length || x >= matrix.length) continue;
        const edge = r === -1 || c === -1 || r === 7 || c === 7;
        const outer = r === 0 || c === 0 || r === 6 || c === 6;
        const inner = r >= 2 && r <= 4 && c >= 2 && c <= 4;
        matrix[y][x] = edge ? 0 : (outer || inner ? 1 : 0);
      }
    }
  }

  function reserveFormat(matrix) {
    const n = matrix.length;
    for (let i = 0; i < 9; i += 1) {
      if (matrix[8][i] === null) matrix[8][i] = 0;
      if (matrix[i][8] === null) matrix[i][8] = 0;
    }
    for (let i = 0; i < 8; i += 1) {
      matrix[8][n - 1 - i] = 0;
      matrix[n - 1 - i][8] = 0;
    }
  }

  function placeFunctions(matrix, version) {
    const n = matrix.length;
    paintFinder(matrix, 0, 0);
    paintFinder(matrix, 0, n - 7);
    paintFinder(matrix, n - 7, 0);
    for (let i = 8; i < n - 8; i += 1) {
      const bit = i % 2 === 0 ? 1 : 0;
      matrix[6][i] = bit;
      matrix[i][6] = bit;
    }
    const centers = ALIGN[version];
    centers.forEach((col, i) => {
      centers.forEach((row, j) => {
        const finderCorner = (i === 0 && j === 0) || (i === 0 && j === centers.length - 1) || (i === centers.length - 1 && j === 0);
        if (finderCorner) return;
        for (let y = -2; y <= 2; y += 1) {
          for (let x = -2; x <= 2; x += 1) {
            const edge = Math.abs(y) === 2 || Math.abs(x) === 2;
            matrix[row + y][col + x] = edge || (y === 0 && x === 0) ? 1 : 0;
          }
        }
      });
    });
    matrix[n - 8][8] = 1;
    reserveFormat(matrix);
    if (version >= 7) {
      for (let i = 0; i < 18; i += 1) {
        const x = n - 11 + (i % 3);
        const y = Math.floor(i / 3);
        matrix[y][x] = 0;
        matrix[x][y] = 0;
      }
    }
  }

  function placeData(matrix, bits) {
    const n = matrix.length;
    let index = 0;
    let upward = true;
    for (let col = n - 1; col > 0; col -= 2) {
      if (col === 6) col = 5;
      for (let step = 0; step < n; step += 1) {
        const row = upward ? n - 1 - step : step;
        for (let dx = 0; dx < 2; dx += 1) {
          const x = col - dx;
          if (matrix[row][x] !== null) continue;
          matrix[row][x] = index < bits.length ? bits[index] : 0;
          index += 1;
        }
      }
      upward = !upward;
    }
  }

  function maskBit(kind, row, col) {
    if (kind === 0) return (row + col) % 2 === 0;
    if (kind === 1) return row % 2 === 0;
    if (kind === 2) return col % 3 === 0;
    if (kind === 3) return (row + col) % 3 === 0;
    if (kind === 4) return (Math.floor(row / 2) + Math.floor(col / 3)) % 2 === 0;
    if (kind === 5) return ((row * col) % 2) + ((row * col) % 3) === 0;
    if (kind === 6) return (((row * col) % 2) + ((row * col) % 3)) % 2 === 0;
    return (((row + col) % 2) + ((row * col) % 3)) % 2 === 0;
  }

  function formatBits(mask) {
    let rem = mask;
    for (let i = 0; i < 10; i += 1) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
    return ((mask << 10) | rem) ^ 0x5412;
  }

  function writeFormat(matrix, mask) {
    const bits = formatBits(mask);
    const n = matrix.length;
    const bit = (index) => (bits >> index) & 1;
    for (let i = 0; i <= 5; i += 1) matrix[i][8] = bit(i);
    matrix[7][8] = bit(6);
    matrix[8][8] = bit(7);
    matrix[8][7] = bit(8);
    for (let i = 9; i < 15; i += 1) matrix[8][14 - i] = bit(i);
    for (let i = 0; i < 8; i += 1) matrix[8][n - 1 - i] = bit(i);
    for (let i = 8; i < 15; i += 1) matrix[n - 15 + i][8] = bit(i);
    matrix[n - 8][8] = 1;
  }

  function versionBits(version) {
    let rem = version;
    for (let i = 0; i < 12; i += 1) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25);
    return (version << 12) | rem;
  }

  function writeVersion(matrix, version) {
    if (version < 7) return;
    const bits = versionBits(version);
    const n = matrix.length;
    for (let i = 0; i < 18; i += 1) {
      const bit = (bits >> i) & 1;
      const x = n - 11 + (i % 3);
      const y = Math.floor(i / 3);
      matrix[y][x] = bit;
      matrix[x][y] = bit;
    }
  }

  function penalty(matrix) {
    const n = matrix.length;
    let score = 0;
    function run(read) {
      let count = 1;
      let prev = read(0);
      for (let i = 1; i < n; i += 1) {
        const bit = read(i);
        if (bit === prev) count += 1;
        else {
          if (count >= 5) score += 3 + (count - 5);
          count = 1;
          prev = bit;
        }
      }
      if (count >= 5) score += 3 + (count - 5);
    }
    for (let r = 0; r < n; r += 1) run((i) => matrix[r][i]);
    for (let c = 0; c < n; c += 1) run((i) => matrix[i][c]);
    for (let r = 0; r < n - 1; r += 1) {
      for (let c = 0; c < n - 1; c += 1) {
        const bit = matrix[r][c];
        if (bit === matrix[r][c + 1] && bit === matrix[r + 1][c] && bit === matrix[r + 1][c + 1]) score += 3;
      }
    }
    const pattern = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0];
    const flipped = [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1];
    function hits(read) {
      for (let i = 0; i <= n - 11; i += 1) {
        let a = true;
        let b = true;
        for (let k = 0; k < 11; k += 1) {
          if (read(i + k) !== pattern[k]) a = false;
          if (read(i + k) !== flipped[k]) b = false;
        }
        if (a || b) score += 40;
      }
    }
    for (let r = 0; r < n; r += 1) hits((i) => matrix[r][i]);
    for (let c = 0; c < n; c += 1) hits((i) => matrix[i][c]);
    let dark = 0;
    matrix.forEach((row) => row.forEach((bit) => { dark += bit; }));
    score += Math.floor(Math.abs((dark * 100) / (n * n) - 50) / 5) * 10;
    return score;
  }

  function build(text) {
    const chosen = choose(text);
    if (!chosen) return null;
    const n = 17 + 4 * chosen.version;
    const base = blank(n);
    placeFunctions(base, chosen.version);
    placeData(base, chosen.bits);
    let best = null;
    let bestScore = Infinity;
    for (let mask = 0; mask < 8; mask += 1) {
      const matrix = base.map((row) => row.slice());
      const reserved = blank(n);
      placeFunctions(reserved, chosen.version);
      for (let r = 0; r < n; r += 1) {
        for (let c = 0; c < n; c += 1) {
          if (reserved[r][c] !== null) matrix[r][c] = base[r][c];
          else matrix[r][c] = (base[r][c] ^ (maskBit(mask, r, c) ? 1 : 0));
        }
      }
      writeFormat(matrix, mask);
      writeVersion(matrix, chosen.version);
      const score = penalty(matrix);
      if (score < bestScore) {
        bestScore = score;
        best = matrix;
      }
    }
    return best;
  }

  function drawAuthenticatorQr(canvas, text) {
    const matrix = build(text);
    if (!matrix || !canvas) return false;
    const quiet = 4;
    const cells = matrix.length + quiet * 2;
    const scale = Math.max(4, Math.floor(196 / cells));
    const size = cells * scale;
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, size, size);
    ctx.fillStyle = "#111111";
    for (let r = 0; r < matrix.length; r += 1) {
      for (let c = 0; c < matrix.length; c += 1) {
        if (matrix[r][c]) ctx.fillRect((c + quiet) * scale, (r + quiet) * scale, scale, scale);
      }
    }
    return true;
  }

  window.drawAuthenticatorQr = drawAuthenticatorQr;
})();
