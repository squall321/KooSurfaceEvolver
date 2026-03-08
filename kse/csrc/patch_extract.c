/*
 * patch_extract.c - Accelerated local patch extraction from STL mesh
 * Part of KooSolderEvolver C extension
 *
 * Compile: included via setup.py Extension
 */

#include <math.h>
#include <string.h>

/* Extract faces within radius of center point */
void extract_patch_faces(
    const double *vertices,      /* (n_verts, 3) */
    const int *faces,            /* (n_faces, 3) */
    int n_faces,
    const double center[3],
    double radius,
    int *mask)                   /* (n_faces,) output: 1=inside, 0=outside */
{
    int fi;
    double r2 = radius * radius;

    for (fi = 0; fi < n_faces; fi++) {
        int i0 = faces[fi * 3];
        int i1 = faces[fi * 3 + 1];
        int i2 = faces[fi * 3 + 2];

        /* Centroid */
        double cx = (vertices[i0*3]   + vertices[i1*3]   + vertices[i2*3])   / 3.0;
        double cy = (vertices[i0*3+1] + vertices[i1*3+1] + vertices[i2*3+1]) / 3.0;
        double cz = (vertices[i0*3+2] + vertices[i1*3+2] + vertices[i2*3+2]) / 3.0;

        double dx = cx - center[0];
        double dy = cy - center[1];
        double dz = cz - center[2];
        double d2 = dx*dx + dy*dy + dz*dz;

        mask[fi] = (d2 <= r2) ? 1 : 0;
    }
}
