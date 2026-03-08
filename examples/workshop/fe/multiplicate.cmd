// multiplicate.cmd

// Surface Evolver script to create datafile with surface duplicated
// according to view transforms in effect.  Writes datafile to stdout.
// Does not create new elements in current surface, since together 
// with view transforms, that would result in quadratic explosion.

// WARNING: This loses all element attributes in the output datafile.
// But does preserve "edgetype" attribute

// usage: multiplicate >>> "newdatafile.fe"

define edge attribute edgetype integer // in case doesn't exist

eps := 1e-4  // tolerance for identifying vertices
multiplicate :=  {

   list topinfo;

   define vertex attribute tx real[transform_count];
   define vertex attribute ty real[transform_count];
   define vertex attribute tz real[transform_count];
   define vertex attribute valias integer[transform_count];
   define edge attribute ehead integer[transform_count];
   define edge attribute etail integer[transform_count];
   define edge attribute ealias integer[transform_count];

   printf "\nVertices\n";
   vstride := max(vertex,id);
   tcount := 1;
   while ( tcount <= transform_count ) do
   { foreach vertex vv do
     { 
       vx := view_transforms[tcount][1][1]*vv.x
                       + view_transforms[tcount][1][2]*vv.y
                       + view_transforms[tcount][1][3]*vv.z
                       + view_transforms[tcount][1][4]*1;
       vy := view_transforms[tcount][2][1]*vv.x
                       + view_transforms[tcount][2][2]*vv.y
                       + view_transforms[tcount][2][3]*vv.z
                       + view_transforms[tcount][2][4]*1;
       vz := view_transforms[tcount][3][1]*vv.x
                       + view_transforms[tcount][3][2]*vv.y
                       + view_transforms[tcount][3][3]*vv.z
                       + view_transforms[tcount][3][4]*1;
       vv.tx[tcount] := vx; vv.ty[tcount] := vy; vv.tz[tcount] := vz;
       vv.valias[tcount] := vv.id + (tcount-1)*vstride;
       // search for alias
       inx := 1;
       while ( inx < tcount ) do
       { if abs(vv.tx[inx]-vx) + abs(vv.ty[inx]-vy) + abs(vv.tz[inx]-vz) < eps
         then { vv.valias[tcount] := vv.valias[inx]; break; };
         inx += 1;
       };
       if ( inx == tcount ) then 
       {  printf "%d  %18.15f %18.15f %18.15f ",vv.id+(tcount-1)*vstride,
             vx,vy,vz;
           printf "\n";
       };
     };
     tcount += 1;
   };

   printf "\nEdges\n";
   estride := max(edge,id);
   tcount := 1;
   while ( tcount <= transform_count ) do
   { foreach edge ee do
     { thishead :=  vertex[ee.vertex[1].id].valias[tcount];
       thistail :=  vertex[ee.vertex[2].id].valias[tcount];
       ee.ealias[tcount] := ee.id + (tcount-1)*estride;
       ee.ehead[tcount] := thishead;
       ee.etail[tcount] := thistail;
       // search for aliases
       inx := 1;
       while ( inx < tcount ) do
       { if ( thishead == ee.ehead[inx] and thistail == ee.etail[inx] ) 
         then { ee.ealias[tcount] := ee.ealias[inx]; break; };
         if ( thishead == ee.etail[inx] and thistail == ee.ehead[inx] ) 
         then { ee.ealias[tcount] := -ee.ealias[inx]; break; };
         inx += 1;
       };
       if ( inx == tcount ) then
       { printf "%d   %d %d edgetype %d",ee.id+(tcount-1)*estride,thishead,
              thistail,edgetype;
         if ee.bare then printf " bare ";
         printf "\n";
       };
     };
     tcount += 1;

   };

   printf "\nFaces\n";
   fstride := max(facet,id);
   tcount := 1;
   while ( tcount <= transform_count ) do
   { tdet := view_transforms[tcount][1][1]*
         (view_transforms[tcount][2][2]*view_transforms[tcount][3][3] 
          - view_transforms[tcount][3][2]*view_transforms[tcount][2][3]) 
        - view_transforms[tcount][1][2]*
         (view_transforms[tcount][2][1]*view_transforms[tcount][3][3] 
          - view_transforms[tcount][3][1]*view_transforms[tcount][2][3]) 
        + view_transforms[tcount][1][3]*
         (view_transforms[tcount][2][1]*view_transforms[tcount][3][2] 
          - view_transforms[tcount][3][1]*view_transforms[tcount][2][2]);
     foreach facet ff do 
     { edge1 := edge[ff.edge[1].id].ealias[tcount];
       edge2 := edge[ff.edge[2].id].ealias[tcount];
       edge3 := edge[ff.edge[3].id].ealias[tcount];
       if ( view_transform_swap_colors[tcount] != (tdet < 0.0) ) then
       // inverted
       printf "%d   %d %d %d\n",ff.id + (tcount-1)*fstride,
         ((ff.edge[3].oid > 0) ? -edge3 : edge3),
         ((ff.edge[2].oid > 0) ? -edge2 : edge2),
         ((ff.edge[1].oid > 0) ? -edge1 : edge1)
       else
       printf "%d   %d %d %d\n",ff.id + (tcount-1)*fstride,
         ((ff.edge[1].oid > 0) ? edge1 : -edge1),
         ((ff.edge[2].oid > 0) ? edge2 : -edge2),
         ((ff.edge[3].oid > 0) ? edge3 : -edge3);
     };
     tcount += 1;
   };

   // not listing bottominfo on purpose; too much extraneous stuff

   // free attribute storage
   define vertex attribute tx real[0];
   define vertex attribute ty real[0];
   define vertex attribute tz real[0];
   define vertex attribute valias integer[0];
   define edge attribute ehead integer[0];
   define edge attribute etail integer[0];
   define edge attribute ealias integer[0];

}

aa := 1
pview := { 
   printf "%f %f %f %f\n",view_transforms[aa][1][1],view_transforms[aa][1][2],
         view_transforms[aa][1][3],view_transforms[aa][1][4];
   printf "%f %f %f %f\n",view_transforms[aa][2][1],view_transforms[aa][2][2],
         view_transforms[aa][2][3],view_transforms[aa][2][4];
   printf "%f %f %f %f\n",view_transforms[aa][3][1],view_transforms[aa][3][2],
         view_transforms[aa][3][3],view_transforms[aa][3][4];
   printf "%f %f %f %f\n",view_transforms[aa][4][1],view_transforms[aa][4][2],
         view_transforms[aa][4][3],view_transforms[aa][4][4];
}

// usage: multiplicate >>> "newdatafile.fe"
