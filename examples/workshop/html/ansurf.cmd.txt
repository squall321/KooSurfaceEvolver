// ansurf.cmd
// Evolver command to produce file of ANSYS input for 
//   vertices, edges,  and faces to produce a surface
//   for ANSYS meshing.
// usage:  ansurf >>> "filename"

// vertices as ANSYS keypoints
ansurf_nodes := { 
       foreach vertex do printf "k,,%20.15g,%20.15g,%20.15g\n",x,y,z;
       }

ansurf_edges := {
       if (quadratic) then 
       foreach edge ee do printf "larc,%g,%g,%g\n",ee.vertex[1].id,
	  ee.vertex[2].id,ee.vertex[3].id
       else
       foreach edge ee do printf "l,%g,%g\n",ee.vertex[1].id,ee.vertex[2].id;
       }

ansurf_faces := {
       foreach facet ff do printf "al,%g,%g,%g\n",
          ff.edge[1].id,ff.edge[2].id,ff.edge[3].id;
       }

// define volumes, one per body
ansurf_bodies := { foreach body bb do
     { // select areas
       flag := 0;
       foreach bb.facet ff do
       { if flag then printf "ASEL,A,AREA,,%g,%g\n",ff.id,ff.id
         else printf "ASEL,S,AREA,,%g,%g\n",ff.id,ff.id;
	 flag := 1;
       };
       printf "VA,ALL\n";
     }
  }

// define areas
ansurf := { printf "/PREP7\n";
            printf "/NOPR\n";
	    ansurf_nodes;
	    ansurf_edges;
	    ansurf_faces;
	    ansurf_bodies;
	    }


