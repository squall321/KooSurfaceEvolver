// gaussref.cmd

// Refining using Gauss map as criterion.
// Refines edges where difference in normal
// exceeds user-set amount.

// Set by user; difference in normals in radians
gaussref_tolerance := 0.3


gaussref := {
   foreach edge eee do
   { ax := eee.vertex[1].vertexnormal[1];
     ay := eee.vertex[1].vertexnormal[2];
     az := eee.vertex[1].vertexnormal[3];
     bx := eee.vertex[2].vertexnormal[1];
     by := eee.vertex[2].vertexnormal[2];
     bz := eee.vertex[2].vertexnormal[3];
     if ( acos(ax*bx+ay*by+az*bz) > gaussref_tolerance )
       then { refine eee; }
   };
}

