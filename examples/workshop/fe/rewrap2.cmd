// rewrap2.cmd

// Commands to rewrap torus vertices and edges to get them nicely
// within unit cell.  2D version.

// Uses torus wrap representation and wrap_vertex builtin command.

rewrap2 := { 
  define body attribute old_volume real; // so can adjust volconst
  set body old_volume volume;
  foreach vertex vv where vv.x*inverse_periods[1][1]+vv.y*inverse_periods[1][2]
       < 0 do wrap_vertex(vv.id,1);
  foreach vertex vv where vv.x*inverse_periods[1][1]+vv.y*inverse_periods[1][2]
       >= 1 do wrap_vertex(vv.id,31);
  foreach vertex vv where vv.x*inverse_periods[2][1]+vv.y*inverse_periods[2][2]
       < 0 do wrap_vertex(vv.id,64);
  foreach vertex vv where vv.x*inverse_periods[2][1]+vv.y*inverse_periods[2][2]
       >= 1 do wrap_vertex(vv.id,1984);
  recalc;
  torvol := abs(torus_periods[1][1]*torus_periods[2][2]
              - torus_periods[1][2]*torus_periods[2][1]);
  set body volconst floor((old_volume - volume - volconst)/torvol+.5)*torvol;

}

