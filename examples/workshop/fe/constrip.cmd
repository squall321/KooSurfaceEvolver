// constrip.cmd

// Creates new facets from edges on constraint 1 to y axis, and colors
// them in alternate strips.
// Meant to be applied to mound.fe.

nextcolor := green;

constrip := {
  foreach edge ee where on_constraint 1 do
  { newv1 := new_vertex(ee.vertex[1].x,0,ee.vertex[1].z);
    newv2 := new_vertex(ee.vertex[2].x,0,ee.vertex[2].z);
    newe1 := new_edge(newv1,ee.vertex[1].id);
    newe2 := new_edge(newv1,newv2);
    newe3 := new_edge(newv2,ee.vertex[2].id);
    newface := new_facet(ee.id,-newe3,-newe2,newe1);
    set facet color nextcolor where original == newface;
    nextcolor := (nextcolor == 14) ? 1 : nextcolor+1;
  };
  set edge ee color clear where ee.valence==2 and
    (ee.facet[1].color==ee.facet[2].color) and
      ee.facet[1].color != white;
}
