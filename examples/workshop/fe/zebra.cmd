// zebra.cmd
// Evolver command to alternately color string edges black and white.

// Usage: set color1 and color2 to the colors you want, and run "zebra"

color1 := black
color2 := white

zebra := {
   color1temp := 4433; // so can identify visited edges.
   color2temp := 4828;
   ecount := 0; // for safety

   do
   { change := 0; // see if anything happens

     // get starting edge
     e_id := 0;
     foreach edge where (color != color1temp) and (color != color2temp) do 
     { e_id := id; break; };
     if e_id == 0 then break;
     first_e := e_id;
     v_id := edge[e_id].vertex[1].id;
     zcolor := color1temp;
     // follow connected edges
     do 
     { set edge[e_id] color zcolor;
       change += 1;
       newe_id := first_e; // safety default
       foreach edge[e_id].vertex[2] vv do  
       { newv_id := vv.id;
         foreach vv.edge ee where (color != color1temp) and 
                  (color != color2temp) 
           do 
             if ee.id != e_id then { newe_id := ee.id; break; }
       };
       if ( newe_id == first_e ) then break;
       e_id := newe_id; v_id := newv_id;
       zcolor := (zcolor == color1temp) ? color2temp : color1temp;
       ecount := ecount + 1;
     } while ( (e_id != first_e) and (ecount <= edge_count + 10) )
   } while change;
   set edge color (color==color1temp) ? color1 : color2;
 }
