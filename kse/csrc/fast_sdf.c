/*
 * fast_sdf.c - Accelerated signed distance field computation
 * Part of KooSolderEvolver C extension
 *
 * Compile: included via setup.py Extension
 */

#include <math.h>
#include <stdlib.h>

/* Compute signed distance from a point to a triangle */
static double point_triangle_distance(
    const double p[3],
    const double v0[3], const double v1[3], const double v2[3],
    const double normal[3])
{
    /* Signed distance to plane */
    double d = (p[0] - v0[0]) * normal[0]
             + (p[1] - v0[1]) * normal[1]
             + (p[2] - v0[2]) * normal[2];
    return d;
}

/* Batch compute signed distances from query points to mesh */
void compute_sdf_batch(
    const double *query_points,  /* (n_queries, 3) */
    int n_queries,
    const double *vertices,      /* (n_verts, 3) */
    const int *faces,            /* (n_faces, 3) */
    int n_faces,
    const double *face_normals,  /* (n_faces, 3) */
    double *distances)           /* (n_queries,) output */
{
    int qi, fi;

    for (qi = 0; qi < n_queries; qi++) {
        const double *p = &query_points[qi * 3];
        double min_dist2 = 1e30;
        int nearest = 0;

        /* Find nearest face centroid */
        for (fi = 0; fi < n_faces; fi++) {
            int i0 = faces[fi * 3];
            int i1 = faces[fi * 3 + 1];
            int i2 = faces[fi * 3 + 2];
            double cx = (vertices[i0*3] + vertices[i1*3] + vertices[i2*3]) / 3.0;
            double cy = (vertices[i0*3+1] + vertices[i1*3+1] + vertices[i2*3+1]) / 3.0;
            double cz = (vertices[i0*3+2] + vertices[i1*3+2] + vertices[i2*3+2]) / 3.0;

            double dx = p[0] - cx;
            double dy = p[1] - cy;
            double dz = p[2] - cz;
            double d2 = dx*dx + dy*dy + dz*dz;

            if (d2 < min_dist2) {
                min_dist2 = d2;
                nearest = fi;
            }
        }

        /* Compute signed distance to nearest triangle */
        {
            int i0 = faces[nearest * 3];
            const double *v0 = &vertices[i0 * 3];
            const double *n = &face_normals[nearest * 3];
            distances[qi] = point_triangle_distance(p, v0, v0, v0, n);
        }
    }
}
