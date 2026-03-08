// orientfix.cmd
// Surface Evolver command to homogenize facet orientations, in alignment
// with first facet.  Works by dissolving facet and re-creating it.
// Of course, this looses a lot of facet attributes.

define facet attribute orientfixed integer;

orientfix := {
  if !linear then
  { printf "'orientfix' currently works only on linear model.\n";
    return;
  };
  set facet orientfixed 0;
  facet[1].orientfixed := 1;
  do
  { changed := 0;
    foreach edge ee where valence == 2 do
    { fixid := 0;
      if ee.facet[1].orientfixed and not ee.facet[2].orientfixed then
      { if ee.facet[1].oid*ee.facet[2].oid > 0 then fixid := ee.facet[2].id
        else { ee.facet[2].orientfixed := 1; changed += 1; }
      }
      else if (not ee.facet[1].orientfixed) and ee.facet[2].orientfixed then
      { if ee.facet[1].oid*ee.facet[2].oid > 0 then fixid := ee.facet[1].id
        else { ee.facet[1].orientfixed := 1; changed += 1; }
      };
      if fixid == 0 then continue;
      
      // now have a facet to flip
      edge1 := facet[fixid].edge[1].oid; 
      edge2 := facet[fixid].edge[2].oid; 
      edge3 := facet[fixid].edge[3].oid; 
      dissolve facet[fixid];
      newf := new_facet(-edge3,-edge2,-edge1);
      facet[newf].orientfixed := 1;
      changed += 1;
    };
  }
  while changed > 0;
}

