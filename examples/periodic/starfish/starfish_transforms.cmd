// starfish_transforms.cmd
// Common commands for use with starfish surfaces.
// Use these after doing "gogo".

// For coloring as on my TPMS webpages
setcolor := { set facet backcolor yellow }

// For displaying full cube unit cell
cube := { 
          transform_expr "abdabdf";
          show_trans "R"; // center it
        }

// For drawing outline cube; do with "cube"
cube_edge := { va := new_vertex(0,2,1);
               vb := new_vertex(0,-2,1);
               ea := new_edge(va,vb);
             }


// For displaying partial unit cell
cubelet := { transform_expr "adadf"; 
             show_trans "R"; // center it
           }

// For drawing outline of cubelet; do with "cubelet" 
cubelet_edge := { va := new_vertex(0,2,1);
                  vb := new_vertex(0,0,1);
                  ea := new_edge(va,vb);
                }

// For displaying rhombic region
rhomb := { 
           transform_expr "abdabdef";
           show_trans "R"; // center it
         }
 
// For drawing outline of rhombic domain
rhomb_edge := { va := new_vertex(0,2,1);
              vb := new_vertex(-1,1,0);
              vc := new_vertex(2,0,-1);
              ea := new_edge(va,vc);
              eb := new_edge(va,vb);
             }

// For drawing fundamental tetrahedron; 
// best to do with "transforms off"
tetra_edge := { va := new_vertex(2,0,-1);
              vb := new_vertex(-2,0,-1);
              vc := new_vertex(0,2,1);
              vd := new_vertex(0,-2,1);
              ea := new_edge(va,vc);
              eb := new_edge(vb,vc);
              ec := new_edge(va,vb);
              ed := new_edge(va,vd);
              eg := new_edge(vb,vd);
              ef := new_edge(vd,vc);
             }

