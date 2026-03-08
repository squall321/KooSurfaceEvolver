// slicer.cmd --- create intersection of surface with plane
// plane eq: aa*x + bb*y + cc*z = dd
// Usage: read "slicer.cmd"; set aa, bb, cc, dd to desired values; slicer;
// output: truncated surface on positive side of plane
// Try not to slice exactly through vertices!!

// Works in torus by rewrapping wrapped edges that would be cut
// so unwrapped part is on positive side of cut plane.

aa := 0; bb := 0; cc := 1; dd := .1;  // set these for desired plane

// First put in new edges along slicing plane
drawslice := { 
        foreach edge ee do 
        {
          xx1 := ee.vertex[1].x; 
          yy1 := ee.vertex[1].y; 
          zz1 := ee.vertex[1].z; 
          xx2 := xx1 + ee.x;  // using edge vector in case of torus wrap
          yy2 := yy1 + ee.y; 
          zz2 := zz1 + ee.z;
          denom := aa*(xx1-xx2)+bb*(yy1-yy2)+cc*(zz1-zz2);
          if ( denom != 0.0 ) then 
          { 
            lambda := (dd-aa*xx2-bb*yy2-cc*zz2)/denom; 
            if ( (lambda >= 0) and (lambda <= 1) ) then 
            { 
              if torus then 
                if ee.wrap then
                { if denom > 0 then // tail on positive side
                    wrap_vertex(ee.vertex[2].id,ee.wrap)
                  else  // head on positive side
                    wrap_vertex(ee.vertex[1].id,wrap_inverse(ee.wrap));
                }; 
         
              xb := lambda*xx1+(1-lambda)*xx2; 
              yb := lambda*yy1+(1-lambda)*yy2;
              zb := lambda*zz1+(1-lambda)*zz2; 
              refine ee;
              ee.vertex[2].x := xb;
              ee.vertex[2].y := yb;
              ee.vertex[2].z := zb;
            } 
            else if torus and ee.wrap then
            { // try wrapping from head
              xx2 := ee.vertex[2].x; 
              yy2 := ee.vertex[2].y; 
              zz2 := ee.vertex[2].z; 
              xx1 := xx2 - ee.x;  // using edge vector in case of torus wrap
              yy1 := yy2 - ee.y; 
              zz1 := zz2 - ee.z;
              denom := aa*(xx1-xx2)+bb*(yy1-yy2)+cc*(zz1-zz2);
              if ( denom != 0.0 ) then 
              { 
                lambda := (dd-aa*xx2-bb*yy2-cc*zz2)/denom; 
                if ( (lambda >= 0) and (lambda <= 1) ) then 
                { 
                  if torus then 
                    if ee.wrap then
                    { if denom > 0 then // tail on positive side
                        wrap_vertex(ee.vertex[2].id,ee.wrap)
                      else  // head on positive side
                        wrap_vertex(ee.vertex[1].id,wrap_inverse(ee.wrap));
                    };
             
                  xb := lambda*xx1+(1-lambda)*xx2; 
                  yb := lambda*yy1+(1-lambda)*yy2;
                  zb := lambda*zz1+(1-lambda)*zz2; 
                  refine ee;
                  ee.vertex[2].x := xb;
                  ee.vertex[2].y := yb;
                  ee.vertex[2].z := zb;
                }
              } 
          }
        } ; 
      } ; 
   }

slicer := {
    drawslice;
    former_autodisplay := (autodisplay);
    autodisplay off; // prevent display while dissolving
    foreach facet ff where   // again, careful of torus wraps
      aa*(ff.vertex[1].x+ff.edge[1].x/3-ff.edge[3].x/3) +
      bb*(ff.vertex[1].y+ff.edge[1].y/3-ff.edge[3].y/3) +
      cc*(ff.vertex[1].z+ff.edge[1].z/3-ff.edge[3].z/3)  < dd do
    { unset ff frontbody;
      unset ff backbody;
      dissolve ff;
    };
    dissolve bodies bbb where sum(bbb.facets,1) == 0;
    dissolve edges;  // just does bare edges
    dissolve vertices; // just does bare vertices
    if former_autodisplay then autodisplay on;
}

color_slice := {
    foreach facet ff where   // again, careful of torus wraps
      aa*(ff.vertex[1].x+ff.edge[1].x/3-ff.edge[3].x/3) +
      bb*(ff.vertex[1].y+ff.edge[1].y/3-ff.edge[3].y/3) +
      cc*(ff.vertex[1].z+ff.edge[1].z/3-ff.edge[3].z/3)  < dd do
       set ff color magenta;      

}
