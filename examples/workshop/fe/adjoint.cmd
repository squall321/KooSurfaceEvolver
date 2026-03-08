// adjoint.cmd

// Calculation of adjoint minimal surface using Konrad Polthier's discrete
// conjugate method of Bonnet rotation.  See
//  Ulrich Pinkall and Konrad Polthier, Computing Discrete Minimal Surfacee 
//  and Their Conjugates, Experim. Math. 2(1) (1993) 15-36
// and 
//  Konrad Polthier, Conjugate Harmonic Maps and Minimal Surfaces.

// This file takes a conforming surface and calculates nonconforming adjoint,
// then tweaks vertices to make it conforming.  The original surface
// should be free of all level set constraints and boundaries.


// For converting to adjoint
define vertex attribute newx real [3];
define edge attribute eflag integer;
define edge attribute enewx real [3];

// Angle of Bonnet rotation, degrees
bangle := 90

// Swaps conjugate sets of coordinates.
flip := {
   foreach vertex vv do 
   { tmp := vv.x; vv.x := vv.newx[1]; vv.newx[1] := tmp; 
     tmp := vv.y; vv.y := vv.newx[2]; vv.newx[2] := tmp; 
     tmp := vv.z; vv.z := vv.newx[3]; vv.newx[3] := tmp; 
   }
}


// Conjugation from conforming to nonconforming.  This should be done
// after removing all constraints and boundaries from vertices.
conconj := {
   set edge eflag 0;
   foreach edge ee do { starte := ee.id; break; };  // just to get starter
   edge[starte].enewx[1] := 0;
   edge[starte].enewx[2] := 0;
   edge[starte].enewx[3] := 0;
   edge[starte].eflag := 1;

   bs := sin(bangle*pi/180);
   bc := cos(bangle*pi/180);  
   ecount := 1;
   endflag := 0;
   loopcount := 1;
   while ( !endflag ) do
   { endflag := 1; 
     foreach facet ff do
     { enum := 1; 
       while ( enum <= 5 ) do
       { thise := (enum imod 3) + 1;
         nexte := ((enum+1) imod 3) + 1;
         othere := ((enum+2) imod 3) + 1;
         if ( ff.edge[thise].eflag>=loopcount and !ff.edge[nexte].eflag ) then
         { nx := ff.x;
           ny := ff.y;
           nz := ff.z;
           norm := sqrt(nx^2+ny^2+nz^2);
           nx := nx/norm; ny := ny/norm; nz := nz/norm;
           ff.edge[nexte].enewx[1] := 
              ff.edge[thise].enewx[1] - (bc*ff.edge[othere].x 
                 + bs*(ff.edge[othere].y*nz - ff.edge[othere].z*ny))/2;
           ff.edge[nexte].enewx[2] := 
              ff.edge[thise].enewx[2] - (bc*ff.edge[othere].y 
                 + bs*(ff.edge[othere].z*nx - ff.edge[othere].x*nz))/2;
           ff.edge[nexte].enewx[3] := 
              ff.edge[thise].enewx[3] - (bc*ff.edge[othere].z 
                 + bs*(ff.edge[othere].x*ny - ff.edge[othere].y*nx))/2;

           ff.edge[nexte].eflag := loopcount+1;
           endflag := 0; 
           ecount += 1;
         };
         enum += 1;
       };  // end while
     };
     printf "%g edges done.\n",ecount;
     loopcount += 1;
   };
   set vertex newx[1] 0;
   set vertex newx[2] 0;
   set vertex newx[3] 0;
   foreach facet ff do 
   { // extend center facet to original vertex; can't simply average
     //   midedge vertices around an original vertex since that doesn't
     //   work for vertices on the boundary.
     vva := 1; while ( vva <= 3 ) do
     { vvb := vva==3 ? 1 : vva+1;
       vvc := vva==1 ? 3 : vva-1;
       kk := 1; while ( kk <= 3 ) do
       {
         ff.vertex[vva].newx[kk] += ff.edge[vva].enewx[kk] 
               - ff.edge[vvb].enewx[kk] + ff.edge[vvc].enewx[kk]; 
         kk += 1;
       };
       vva += 1;
     }
   };
   foreach vertex vv do
   { 
     nbrs := sum(vv.facet, 1);
     if ( nbrs != 0 ) then
     { vv.newx[1] /= nbrs;
       vv.newx[2] /= nbrs;
       vv.newx[3] /= nbrs;
     };
   };
  
} // end conconj


adjoint := { 
   autodisplay_state := (autodisplay);
   autodisplay off;
   conconj;
   flip;
   if ( autodisplay_state ) then autodisplay;
}

   
