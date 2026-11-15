// GPU reference workload: Mandelbrot iteration counts on the Metal GPU (float32).
// usage: metal_mandel <n> <iters>
// prints one JSON line. The shader is compiled at run time (no Xcode toolchain needed).
import Foundation
import CoreGraphics
import Metal

let shader = """
#include <metal_stdlib>
using namespace metal;
struct P { uint n; uint iters; };
kernel void mandel(device uint *out [[buffer(0)]], constant P &p [[buffer(1)]],
                   uint2 gid [[thread_position_in_grid]]) {
    if (gid.x >= p.n || gid.y >= p.n) return;
    float ci = -1.3f + 2.6f * float(gid.y) / float(p.n);
    float cr = -2.0f + 2.6f * float(gid.x) / float(p.n);
    float zr = 0.0f, zi = 0.0f;
    uint k = 0;
    while (k < p.iters && zr * zr + zi * zi <= 4.0f) {
        float t = zr * zr - zi * zi + cr;
        zi = 2.0f * zr * zi + ci;
        zr = t;
        k++;
    }
    out[gid.y * p.n + gid.x] = k;
}
"""

struct P { var n: UInt32; var iters: UInt32 }

func now() -> Double { return Double(DispatchTime.now().uptimeNanoseconds) / 1e9 }

let args = CommandLine.arguments
let n = args.count > 1 ? Int(args[1])! : 1024
let iters = args.count > 2 ? Int(args[2])! : 300

// In a command-line tool the default device can be nil; enumerate explicitly as a fallback.
guard let dev = MTLCreateSystemDefaultDevice() ?? MTLCopyAllDevices().first else {
    print("{\"ok\": false, \"error\": \"no Metal device\"}")
    exit(1)
}
let t0 = now()
let lib: MTLLibrary
do { lib = try dev.makeLibrary(source: shader, options: nil) } catch {
    print("{\"ok\": false, \"error\": \"shader compile failed\"}")
    exit(1)
}
let fn = lib.makeFunction(name: "mandel")!
let pipe = try! dev.makeComputePipelineState(function: fn)
let setupS = now() - t0

let out = dev.makeBuffer(length: n * n * 4, options: .storageModeShared)!
var p = P(n: UInt32(n), iters: UInt32(iters))
let queue = dev.makeCommandQueue()!

func run() -> Double {
    let t = now()
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipe)
    enc.setBuffer(out, offset: 0, index: 0)
    enc.setBytes(&p, length: MemoryLayout<P>.size, index: 1)
    let w = pipe.threadExecutionWidth
    let h = pipe.maxTotalThreadsPerThreadgroup / w
    enc.dispatchThreadgroups(MTLSize(width: (n + w - 1) / w, height: (n + h - 1) / h, depth: 1),
                             threadsPerThreadgroup: MTLSize(width: w, height: h, depth: 1))
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    return now() - t
}

var times: [Double] = []
for _ in 0..<3 { times.append(run()) }
let ptr = out.contents().bindMemory(to: UInt32.self, capacity: n * n)
var total: UInt64 = 0
for i in 0..<(n * n) { total += UInt64(ptr[i]) }
times.sort()
print("{\"ok\": true, \"device\": \"\(dev.name)\", \"n\": \(n), \"iters\": \(iters), \"checksum\": \(total), " +
      "\"gpu_s_median\": \(times[1]), \"gpu_s_all\": \(times), \"setup_s\": \(setupS), " +
      "\"low_power\": \(dev.isLowPower), \"max_buffer_MB\": \(dev.maxBufferLength / 1_000_000)}")
