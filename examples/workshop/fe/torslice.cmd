// torslice.cmd
// For slicing out a slab from twointor.

read "slicer.cmd"

torslice_y := {
           if ( yleft >= yright ) then
           { errprintf"torslice_y error: cannot have yleft greater than yright.\n";
             return;
           };
           /* rewrap any wrapped edges that will be cut */
           foreach edge ee where (ee.wrap idiv 64) imod 64 do
           { if (ee.vertex[1].y > yleft and ee.vertex[1].y < yright)
             or (ee.vertex[2].y > yleft and ee.vertex[2].y < yright) then
             { errprintf "slice error: edge %d is wrapped but intersects slice.\n";
               return;
             }
           };

           old_autodisplay := (autodisplay);
           autodisplay off;
           aa:=0; bb:=1; cc:=0; dd:=yleft; slicer;
           set edge constraint 1 where valence == 1;

           aa:=0; bb:=-1; cc:=0; dd:=-yright; slicer;
           set edge constraint 2 where valence == 1 and not on_constraint 1;
           flush_counts;
           if old_autodisplay then autodisplay on;

           // Don't do vertex con 1 until after got rid of everything!!
           foreach edge ee where on_constraint 1 do set ee.vertex constraint 1;
           foreach edge ee where on_constraint 2 do set ee.vertex constraint 2;

           // Now get volumes to work right by getting left margin to y = 0
           set vertex y y-yleft;
           yright -= yleft;
           yleft := 0;
           if sum(body where volume < 0,1) > 1 then
             errprintf "Multiple bodies with negative volume!!\n"
           else
           foreach body bbb where bbb.volume < 0 do
           { /* should be only one */
             bbb.volconst += yright*torus_periods[1][1]*torus_periods[3][3];
           };
           set body target volume;
         }



