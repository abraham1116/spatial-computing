/* Portable reference workload: same Mandelbrot checksum as spatial/compute/workloads.py.
 * Built for Mach-O (native), Linux ELF, Windows PE and WASM/WASI from this single source.
 * Output: "RESULT <checksum> <elapsed_ms>"                                              */
#include <stdio.h>
#include <stdlib.h>

#ifdef _WIN32
#include <windows.h>
static double now_ms(void) {
    LARGE_INTEGER f, c;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return 1000.0 * (double)c.QuadPart / (double)f.QuadPart;
}
#else
#include <time.h>
static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}
#endif

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 600;
    int iters = argc > 2 ? atoi(argv[2]) : 300;
    const double X0 = -2.0, X1 = 0.6, Y0 = -1.3, Y1 = 1.3;
    double t0 = now_ms();
    long long total = 0;
    for (int i = 0; i < n; i++) {
        double ci = Y0 + (Y1 - Y0) * i / n;
        for (int j = 0; j < n; j++) {
            double cr = X0 + (X1 - X0) * j / n;
            double zr = 0.0, zi = 0.0;
            int k = 0;
            while (k < iters && zr * zr + zi * zi <= 4.0) {
                double t = zr * zr - zi * zi + cr;
                zi = 2.0 * zr * zi + ci;
                zr = t;
                k++;
            }
            total += k;
        }
    }
    printf("RESULT %lld %.3f\n", total, now_ms() - t0);
    return 0;
}
