Notes on Surface Evolver datafiles for Starfish surfaces:

Starfish webpage is http://www.susqu.edu/brakke/evolver/examples/periodic/starfish/starfish.html

The datafiles are named by genus:

 starfish31adj.fe
 starfish43adj.fe
 starfish47adj.fe
 starfish55adj.fe
 starfish59adj.fe
 starfish63adj.fe
 starfish71adj.fe
 starfish75adj.fe
 starfish87adj.fe

 Genus 67,79,91, and 115 are missing at the moment.

 Auxiliary files that all these datafiles need:
   adjoint.cmd
   starfish_transforms.cmd

Each datafile has a command "gogo" that will evolve a fundamental region.

After "gogo" you may display various size pieces with these commands:
   cubelet - what's shown on the main starfish page; 1/8 of unit cell.
   cube    - full unit cell, as seen on
             http://www.susqu.edu/brakke/evolver/examples/periodic/starfish/starfishcube.html
             To get the cube outline edges, also run "cube_edge".
   rhomb   - rhombic unit cell, as seen on
             http://www.susqu.edu/brakke/evolver/examples/periodic/starfish/starfishrhomb.html
             To get the rhombus outline edges, also run "rhomb_edge".

   Since these display lots of facets and might make graphics sluggish, you probably 
   want to turn off displaying all edges by hitting the "e" key in the graphics window. 

To get coloring as on the web pages, do "setcolor".
