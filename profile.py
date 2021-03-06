#!/usr/bin/env python
"""
Calculates and displays diffraction pattern profiles
"""

from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg

from matplotlib.backends.backend_wx import _load_bitmap
from matplotlib.figure import Figure

import wx
import os

import numpy as np
from scipy.optimize import leastsq
import scipy.special
#import scipy.linalg

import matplotlib.pyplot as plt

from polar_pattern import reproject_image_into_polar
import sim_index as sim_i

import ring_pattern

import time

import subprocess

from io import BytesIO
from scipy import special

class Timer():
   def __enter__(self): self.start = time.time()
   def __exit__(self, *args): print(time.time() - self.start)

from matplotlib import rc

rc('savefig', dpi=600)
rc("xtick", direction="out")
rc("ytick", direction="out")
rc("lines", markeredgewidth=1)

ID_SAVE=105
ID_LABEL=106
ID_SUB=107
ID_RECEN=111
ID_CLRP=112
ID_PUN=113
ID_POL=114
ID_SIM=115
ID_SIML=116
ID_PPREF=117
ID_CLRS=118
ID_BSC=119
ID_RSP=120
ID_SIM2=121
ID_PROSIM=122
ID_RING=123
ID_CLRPS=124

#global radframe
#global centers

def integrate(frame, pattern_open, circles, pixel_size, size):
    
#    global radframe
    print(frame)
    if pattern_open.any(): 
        if circles:
            print('Integration started. please wait...')
            radframe = radial(frame, pattern_open, circles, pixel_size, size)
            radframe.Show(True)
        else:
            error_cir = 'Please mark at lease one ring.'
            print(error_cir)
            error_int_dlg = Error(frame, -1, 'Error', error_cir)
            error_int_dlg.Show(True)
            error_int_dlg.Centre()
    else:
        error_pat = 'Please open a diffraction image file.'
        print(error_pat)
        error_int_dlg = Error(frame, -1, 'Error', error_pat)
        error_int_dlg.Show(True)
        error_int_dlg.Centre()
            
class Error(wx.Dialog):
    def __init__(self, parent, id, title, message):
        wx.Dialog.__init__(self, parent, -1, 'Integrate', wx.DefaultPosition, wx.Size(450, 125))
        wx.StaticText(self, -1, message, (20,20))
        clear_btn = wx.Button(self, 2, 'Close', (190, 75))
        self.Bind(wx.EVT_BUTTON, self.OnClose, id=2)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
    def OnClose(self, event):
        self.Destroy()
            
class MyNavigationToolbar2(NavigationToolbar2WxAgg):
    """
    Extend the default wx toolbar with your own event handlers
    """
    ON_LABELPEAKS = wx.NewId()
    ON_CLEAR = wx.NewId()
    ON_UNDO = wx.NewId()
    def __init__(self, parent, canvas, cankill):
        NavigationToolbar2WxAgg.__init__(self, canvas)
        
        self.parent = parent
        
        if self.parent.mpl_old:
           self.wx_ids = {'Pan' : self._NTB2_PAN,'Zoom': self._NTB2_ZOOM}
        
        self.AddSeparator()
        if 'phoenix' in wx.PlatformInfo:
            self.AddCheckTool(self.ON_LABELPEAKS, 'Label Peaks', _load_bitmap(os.path.join(self.parent.parent.iconspath, 'profile_label.png')),
                shortHelp= 'Label Peaks',longHelp= 'Click on a peak to label the d-spacing')
        else:
            self.AddCheckTool(self.ON_LABELPEAKS, _load_bitmap(os.path.join(self.parent.parent.iconspath, 'profile_label.png')),
                shortHelp= 'Label Peaks',longHelp= 'Click on a peak to label the d-spacing')
        self.Bind(wx.EVT_TOOL, self._on_labelpeaks, id=self.ON_LABELPEAKS)
        self.AddSeparator()
        if 'phoenix' in wx.PlatformInfo:
            self.AddTool(self.ON_CLEAR, 'Clear Profiles', _load_bitmap(os.path.join(self.parent.parent.iconspath, 'profile_good.png')),
                        'Clear all except the last profile')
        else:
            self.AddSimpleTool(self.ON_CLEAR, _load_bitmap(os.path.join(self.parent.parent.iconspath, 'profile_good.png')),
                        'Clear Profiles', 'Clear all except the last profile')
        self.Bind(wx.EVT_TOOL, self._on_clear, id=self.ON_CLEAR)
        undo_ico = wx.ArtProvider.GetBitmap(wx.ART_UNDO, wx.ART_TOOLBAR, (16,16))
        if 'phoenix' in wx.PlatformInfo:
            self.AddTool(self.ON_UNDO, 'Undo', undo_ico,
                         'Go back to the previous profile')
        else:
            self.AddSimpleTool(self.ON_UNDO, undo_ico,
                        'Undo', 'Go back to the previous profile')
        self.Bind(wx.EVT_TOOL, self._on_undo, id=self.ON_UNDO)
        
    def zoom(self, *args):
        self.ToggleTool(self.wx_ids['Pan'], False)
        self.ToggleTool(self.ON_LABELPEAKS, False)
        NavigationToolbar2WxAgg.zoom(self, *args)

    def pan(self, *args):
        self.ToggleTool(self.wx_ids['Zoom'], False)
        self.ToggleTool(self.ON_LABELPEAKS, False)
        NavigationToolbar2WxAgg.pan(self, *args)

    def _on_labelpeaks(self, evt):
        print('Select peaks to label')
        
        self.ToggleTool(self.wx_ids['Zoom'], False)
        self.ToggleTool(self.wx_ids['Pan'], False)
        
        #eid = radframe.canvas.mpl_connect('button_press_event', onclick_lable)
        
        if self._active == 'MARK':
            self._active = None
        else:
            self._active = 'MARK'
        if self._idPress is not None:
            self._idPress = self.canvas.mpl_disconnect(self._idPress)
            self.mode = ''

        if self._active:
            self._idPress = self.canvas.mpl_connect(
                'button_press_event', self.parent.onclick_lable)
            self.mode = 'label peaks'
            self.canvas.widgetlock(self)
        else:
            self.canvas.widgetlock.release(self)

        for a in self.canvas.figure.get_axes():
            a.set_navigate_mode(self._active)

            self.set_message(self.mode)
        

    def _on_subtract(self, evt):
        self.parent.bgfitp = np.array([])
        print('Select points on the background')
        try:
            #print(self.fid)
            if self.fid != None:
                self.fid = self.canvas.mpl_disconnect(self.fid)
            self.fid = self.canvas.mpl_connect('button_press_event', self.parent.onclick_fitback)
        except AttributeError:
            self.fid = self.canvas.mpl_connect('button_press_event', self.parent.onclick_fitback)
        #print(self.fid)
        
    def _on_clear(self, evt):
        self.parent.OnClearPro(evt)
        
    def _on_undo(self, evt):
        self.parent.OnUndo(evt)


    def mouse_move(self, event):
        #print('mouse_move', event.button)

        if not event.inaxes or not self._active:
            if self._lastCursor != cursors.POINTER:
                self.set_cursor(cursors.POINTER)
                self._lastCursor = cursors.POINTER
        else:
            if self._active=='ZOOM':
                if self._lastCursor != cursors.SELECT_REGION:
                    self.set_cursor(cursors.SELECT_REGION)
                    self._lastCursor = cursors.SELECT_REGION
                if self._xypress:
                    x, y = event.x, event.y
                    lastx, lasty, a, ind, lim, trans = self._xypress[0]
                    self.draw_rubberband(event, x, y, lastx, lasty)
            elif (self._active=='PAN' and
                    self._lastCursor != cursors.MOVE):
                self.set_cursor(cursors.MOVE)

                self._lastCursor = cursors.MOVE

            elif (self._active=='MARK' and 
                    self._lastCursor != cursors.BULLSEYE):
                self.set_cursor(cursors.BULLSEYE)

                self._lastCursor = cursors.BULLSEYE    
                
        if event.inaxes:

            try: s = event.inaxes.format_coord(event.xdata, event.ydata)
            except ValueError: pass
            except OverflowError: pass
            else:
                if len(self.mode):
                    self.parent.statbar.SetStatusText('%s, %s' % (self.mode, s), 1)
                else:
                    self.parent.statbar.SetStatusText(s, 1)
        else: self.parent.statbar.SetStatusText(self.mode,1)
        
    def set_cursor(self, cursor):
        cursor =wx.Cursor(cursord[cursor])
        self.canvas.SetCursor( cursor )

# cursors
class Cursors:  #namespace
    HAND, POINTER, SELECT_REGION, MOVE, BULLSEYE = range(5)
cursors = Cursors()

#print(cursord)
cursord = {
    cursors.MOVE : wx.CURSOR_HAND,
    cursors.HAND : wx.CURSOR_HAND,
    cursors.POINTER : wx.CURSOR_ARROW,
    cursors.SELECT_REGION : wx.CURSOR_CROSS,
    cursors.BULLSEYE : wx.CURSOR_BULLSEYE,        
    }
    
print(cursord)

class radial(wx.Frame):

    def __init__(self, parent, pattern_open, circles, pixel_size, size):
        wx.Frame.__init__(self,parent,-1,
            "Intensity Profile - "+parent.filename ,size=(700,500))
                
        iconFile = os.path.join(parent.iconspath, "diff_profiler_ico.ico")
        icon1 = wx.Icon(iconFile, wx.BITMAP_TYPE_ICO)
        
        self.SetIcon(icon1)
        
        self.simulations = []
        self.plot_sim = 0
        self.prosim = 0
        
        self.parent = parent
        
        self.mpl_old = self.parent.mpl_old
        
        self.dirname = self.parent.dirname
        self.filename = self.parent.filename
        # TODO no clipping
        self.pattern_open = np.clip(pattern_open, self.parent.img_contrast[0], self.parent.img_contrast[1]) - self.parent.img_contrast[0]
        self.circles = circles
        
        self.pixel_size = pixel_size
        
        self.plot_polar = 0
        self.show_polar = 1
        self.limit = 0
        self.gamma = 0.1        
        self.latex = 0
        self.polar_neg = 1
        self.angstrom = u'\u00c5'
        self.sctr_vec = 0
        self.use_voigt = 1
        self.background_sub = 0
            

        self.statbar = self.CreateStatusBar() # A Statusbar in the bottom of the window
        self.statbar.SetFieldsCount(2)
        self.statbar.SetStatusText("None", 1)
        
        # Setting up the menu. filemenu is a local variable at this stage.
        intmenu= wx.Menu()
        # use ID_ for future easy reference - much better than "48", "404" etc
        # The & character indicates the short cut key
        intmenu.Append(ID_SIM, "Import &Crystal File(CIF)"," Simulate Peaks and Profile from a CIF file")
        intmenu.Append(ID_SIM2, "Import &GDIS Simulation"," Open a peak simulation from GDIS")
        intmenu.Append(ID_PROSIM, "Import GDIS &Profile Sim"," Open a profile simulation from GDIS")
        
        intmenu.Append(ID_SAVE, "&Export Data"," Export Profile Data to a text file")
        
        # Setting up the menu. filemenu is a local variable at this stage.
        editmenu= wx.Menu()
        # use ID_ for future easy reference - much better than "48", "404" etc
        # The & character indicates the short cut key
        editmenu.Append(ID_PUN, "&Undo Profile"," Go back to the previous profile")        
        editmenu.Append(ID_SIML, "Simulation &Labels"," Edit simulation labels and indices")
        editmenu.Append(ID_PPREF, "&Profile Prefrences"," Edit profile prefrences and limits")        
        editmenu.Append(ID_CLRP, "&Clear Profiles"," Clear all except the last profile")        
        editmenu.Append(ID_CLRS, "&Remove Simulation"," Remove the last simulation")
        editmenu.Append(ID_CLRPS, "R&emove Profile Sim"," Remove the profile simulation")
        
        # Setting up the menu. filemenu is a local variable at this stage.
        toolsmenu= wx.Menu()
        # use ID_ for future easy reference - much better than "48", "404" etc
        # The & character indicates the short cut key
        #toolsmenu.Append(ID_LABEL, "&Label Peaks"," Label peak on the diffraction")
        toolsmenu.Append(ID_SUB, "&Background Subtract"," Subtract background from the diffraction")
        toolsmenu.Append(ID_RECEN, "&Recenter(Sharpen Peaks)"," Sharpen profile peaks by recentering")
        toolsmenu.Append(ID_POL, "&Polar Pattern"," Display polar pattern to compare with the profile")        
        toolsmenu.Append(ID_BSC, "Beam Stop &Correction"," Use the polar pattern to correct for a beam stopper")
        toolsmenu.Append(ID_RSP, "Remove &Spots","Removes a spot pattern from the profile")
        toolsmenu.Append(ID_RING, "Make a Ring &Figure","Uses the pattern and the fitted simulations to make a ring figure")
        # Creating the menubar.
        menuBar = wx.MenuBar()
        menuBar.Append(intmenu,"&Profile") # Adding the "patternmenu" to the MenuBar
        menuBar.Append(editmenu,"&Edit")
        menuBar.Append(toolsmenu,"&Tools") # Adding the "patternmenu" to the MenuBar
        self.SetMenuBar(menuBar)  # Adding the MenuBar to the Frame content.
        # Note - previous line stores the whole of the menu into the current object
        
        #self.SetBackgroundColour(wx.Colour("WHITE"))

        self.figure = Figure(figsize=(8,6), dpi=76)
        self.figure.patch.set_facecolor('#F2F1F0')
        self.axes = self.figure.add_subplot(111)
        
        self.canvas = FigureCanvas(self, -1, self.figure)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.canvas, 1, wx.TOP | wx.LEFT | wx.EXPAND)
        
        # Capture the paint message
        self.Bind(wx.EVT_PAINT, self.OnPaint)

        self.toolbar = MyNavigationToolbar2(self, self.canvas, True)
        self.toolbar.Realize()
        
        tw, th = self.toolbar.GetSize()
        fw, fh = self.canvas.GetSize()
        self.toolbar.SetSize(wx.Size(fw, th))
        self.sizer.Add(self.toolbar, 0, wx.LEFT | wx.EXPAND)
        
        # update the axes menu on the toolbar
        self.toolbar.update()
        
        # Define the code to be run when a menu option is selected
        self.Bind(wx.EVT_MENU, self.OnSave, id=ID_SAVE)
        self.Bind(wx.EVT_MENU, self.OnSimOpen, id=ID_SIM)
        self.Bind(wx.EVT_MENU, self.OnSim2Open, id=ID_SIM2)
        self.Bind(wx.EVT_MENU, self.OnProSimOpen, id=ID_PROSIM)
        self.Bind(wx.EVT_MENU, self.toolbar._on_labelpeaks, id=ID_LABEL)
        self.Bind(wx.EVT_MENU, self.toolbar._on_subtract, id=ID_SUB)
        self.Bind(wx.EVT_MENU, self.OnRecenter, id=ID_RECEN)
        self.Bind(wx.EVT_MENU, self.OnClearPro, id=ID_CLRP)
        self.Bind(wx.EVT_MENU, self.OnUndo, id=ID_PUN)
        self.Bind(wx.EVT_MENU, self.OnPolar, id=ID_POL)
        self.Bind(wx.EVT_MENU, self.OnSimLabel, id=ID_SIML)
        self.Bind(wx.EVT_MENU, self.OnPro_Pref, id=ID_PPREF)
        self.Bind(wx.EVT_MENU, self.OnClearSim, id=ID_CLRS)
        self.Bind(wx.EVT_MENU, self.OnBeamStop, id=ID_BSC)
        self.Bind(wx.EVT_MENU, self.OnRemoveSpots, id=ID_RSP)
        self.Bind(wx.EVT_MENU, self.OnRingPattern, id=ID_RING)
        self.Bind(wx.EVT_MENU, self.OnClearProSim, id=ID_CLRPS)
        self.SetSizer(self.sizer)
        self.Fit()

        self.center(self.pattern_open, circles, pixel_size)
        self.plot()
    
    def center(self, pattern_open, circles, pixel_size):
        
        centers = np.array([])
        dspace = []
        
        for circle in circles:
            if not centers.size: centers = np.array([circle.center])
            else: centers = np.vstack((centers, np.array([circle.center])))
            dspace += [circle.dspace]
        
        dspace = np.array(dspace)* 10**10    
        dspace.sort()
        print(1/dspace[-1])
        
        self.sctr_vec = 1/dspace[-1]
        
        C = centers[:].sum(axis=0)/centers[:].shape[0]
        self.C = C
        print(centers, C)
        
        self.intensity(pattern_open, C, pixel_size)
        
        self.rdfb = [self.rdf.copy()]
        self.drdfb = [self.drdf.copy()]
        
    def OnRecenter(self, event):
        
        C = self.C
        
        self.intensity(self.pattern_open, self.C, self.pixel_size)
        self.plot(3,'r')
        
        search_range = 2
        divs = [[4,'g'],[2,'c'],[1,'m']]
        # dialog = wx.ProgressDialog('Recentering (May take a few minutes)', 
        #        'Depending on the size of your image this may take a few minutes.', maximum = 28, parent = self)

        y = 0
        cilist = np.zeros(9) #list of center index...looking for duplicates
        
        for i in range(20):
            x=0
            div = divs[y]
            #dialog.Update ( x + y*len(cilist), 'On Division ' + str ( y + 1 ) + ' of ' + str(len(divs)) + '.' )
            clin = (np.arange(search_range + 1) - search_range/2) * div[0]
            C_arrayx = np.ones((search_range + 1,search_range + 1)) * (C[0] + clin).reshape(-1,1)
            C_arrayy = np.ones((search_range + 1,search_range + 1)) * (C[1] + clin)    
            C_array = np.c_[C_arrayx.reshape(-1,1),C_arrayy.reshape(-1,1)]
            #print(div, clin, C_array, C_array.shape)
            peak=[]
            peak_sctr_vec=[]
            
            for cen in C_array:
                self.intensity(self.pattern_open, cen, self.pixel_size)
                peak_i = self.peak_fit(self.sctr_vec, fit_range = 4)
                peak_sctr_vec += [self.t[peak_i]]
                #print(self.peak_parab[peak_i])
                peak += [self.peak_parab[peak_i]]
                self.plot(1,div[1])
                #dialog.Update ( x + y*len(cilist))
                x += 1
                
            peak = np.array(peak)
            index = np.nonzero(peak == peak.max())
            
            #print(peak, peak.max(), C_array[index], peak_sctr_vec, array(peak_sctr_vec)[index])
            C = C_array[index][0]
            self.C = C
            
            self.sctr_vec = np.array(peak_sctr_vec)[index]
            self.axes.vlines(self.sctr_vec,0,1)
            self.axes.figure.canvas.draw()
            
            print(index)
            if index[0] == 4:
                y += 1
                cilist = np.zeros(9)
            elif index[0] == 3 or index[0] == 5:
                cilist[index[0]] += 1
            print(cilist)
            if (cilist > 1).any():
                print('LOOP CONDITION AVERTED')
                y += 1
                cilist = np.zeros(9)
            print('y = ', y,'i = ', i)
            if y>2 or i==19:
                #dialog.Update (28)
                break
            
        self.intensity(self.pattern_open, C_array[index][0], self.pixel_size)
        
        self.rdfb += [self.rdf.copy()]
        self.drdfb += [self.drdf.copy()]
        
        self.plot_polar = 0
        
        self.plot(5,'k')        
        self.axes.figure.canvas.draw()
            
    def intensity(self, pattern_open, C, pixel_size):
        
        Nx = pattern_open.shape[1]
        Ny = pattern_open.shape[0]
        print(C, C[0], C[1]        )
        boxx = Nx/2. - abs(Nx/2. - C[0])-2
        boxy = Ny/2. - abs(Ny/2. - C[1])-2
        if boxx <= boxy:
            boxs = np.floor(boxx)
        else:
            boxs = np.floor(boxy)
            
        self.boxs = boxs
    
        B = int(np.floor(boxs/2))
        Dd = boxs/B
        rdf = np.zeros((B))
    
        #x = random.rand(N)*lx
        #y = random.rand(N)*ly
        
        #print(Nx, Ny, boxs, Dd, C, len(range(Nx)), len(range(Ny)))
        
        y = ((np.ones((Ny,Nx)) * np.arange(Ny).reshape(-1,1)) - C[1])**2
        x = ((np.ones((Ny,Nx)) * np.arange(Nx)) - C[0])**2
        with Timer():
            d = np.around(np.sqrt(x + y)/Dd)
        #print(d.shape)

        r = np.arange(B)
        #print(d, pattern_open/255.)
        
        with Timer():
            self.rdf, bin_edge = np.histogram(d, bins = B, range=(0,B), weights=pattern_open/float(pattern_open.max()))
        #print(self.rdf, rdf.size, bin_edge, bin_edge.size)

        r[0] = 1
        self.rdf /= r
        
        self.rdf_max = self.rdf.max()
                
        self.drdf = (np.arange(B)*Dd) * (pixel_size / 10**10)
        
        #print(self.rdf)
        #print(self.rdf, self.drdf , len(self.rdf), len(self.drdf))
        
    def plot(self, lw=1, col='b'):
        
        if self.latex:
            rc('text', usetex=True)
            rc('font', family='serif')
            self.angstrom = r'\AA'
        else:
            rc('text', usetex=False)
            rc('font', family='sans-serif')
            rc('mathtext', fontset = 'custom')
            self.angstrom = u'\u00c5'
        
        self.rdf /= self.rdf.max()
            
        self.axes.plot(self.drdf, self.rdf, c=col, alpha=1, linewidth=lw, zorder = 50)
        self.axes.set_title('Diffraction Pattern Intensity Profile')
        self.axes.set_xlabel('Scattering Vector (1/'+self.angstrom+')',size=16)
        self.axes.set_ylabel('Intensity',size=16)
        self.axes.set_yticks([])
        #print("Press 'm' mark peaks.")
        #axi2.set_xlim(0,5)
        if self.plot_polar and self.show_polar:
            if self.polar_neg: cmap='binary'
            else: cmap='gray'
            #print(cmap, self.polar_neg)
            log_polar = np.rot90(np.log(1+self.gamma*self.polar_grid))
            self.axes.imshow(log_polar, cmap=cmap, origin='lower', interpolation='bicubic',
                extent=(0, self.drdf.max(), 0, self.rdf.max()+self.rdf.max()*.2))
        if self.prosim:
            self.axes.plot(self.prosim_inv_d,self.prosim_int, linewidth=1, c='r', zorder = 40)
            self.axes.figure.canvas.draw()
                    
        if self.plot_sim:
            points = []
            sim_name = []
            color = ['#42D151','#2AA298','#E7E73C']
            marker = ['o','^','s']
            print(len(self.simulations))#, self.srdfb
            if len(self.simulations) >= 3:
                sim_len_i = 3
            else:
                sim_len_i = len(self.simulations)
            print(sim_len_i)#,self.srdfb[sim_len_i[0]],self.sdrdfb[sim_len_i[0]]
            for col_index, simulation in enumerate(self.simulations[-sim_len_i:]):
                sim_color = simulation.sim_color if simulation.sim_color else color[col_index]
                sim_name += [simulation.sim_label]
                sim = simulation.srdf
                sim_norm = sim/float(max(sim))
                #print(sim, max(sim[1:]), min(sim[1:]), sim_norm)
                self.axes.vlines(simulation.sdrdf, 0, sim_norm*simulation.sim_intens, sim_color ,linewidth = 2, zorder = 2)
                #sim_index = nonzero(self.srdfb[i]!=0)
                points += [self.axes.plot(simulation.sdrdf, sim_norm*simulation.sim_intens, marker[col_index],  c=sim_color, ms = 8, zorder = 3)[0]]
                for i,label in enumerate(simulation.peak_index_labels):
                    #print(label)
                    if label:
                        if label.find('-') == -1:
                            label = r'('+label+')'
                        else:
                            label = r'$\mathsf{('+label.replace('-',r'\bar ')+')}$'
                        #print(label)
                        bbox_props = dict(boxstyle="round", fc=sim_color, ec="0.5", alpha=0.7)
                        self.axes.text(simulation.sdrdf[i], sim_norm[i]*simulation.sim_intens + .05, label, ha="center", va="bottom", size=12, rotation=90, zorder = 100,
                            bbox=bbox_props)
        
            print(sim_name, points )
            leg = self.axes.legend(points , sim_name, loc='upper right', shadow=0, fancybox=True, numpoints=1)    
            frame = leg.get_frame()
            frame.set_alpha(0.4)
        
        if not self.limit: self.limit = self.drdf.max()
        
        self.axes.axis('auto')
        self.axes.set_xlim(0, self.limit+0.0001)
        self.axes.set_ylim(0, self.rdf.max()+self.rdf.max()*.2)
        self.figure.tight_layout()
        plt.show()
        #self.axes.figure.canvas.draw()
        
    def OnPaint(self, event):
        self.canvas.draw()
        event.Skip()

    def OnSave(self,e):
    # Save away the edited text
    # Open the file, do an RU sure check for an overwrite!
        filename = os.path.splitext(self.filename)
        dlg = wx.FileDialog(self, "Choose a file", self.dirname, filename[0] + '.txt', "*.*", \
            wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            # Grab the content to be saved
            #itcontains = self.control.GetValue()
            
            
            self.filename=dlg.GetFilename()
            self.dirname=dlg.GetDirectory()
            with open(os.path.join(self.dirname, self.filename), 'w') as outfile:
                data = np.array([self.rdf, self.drdf])
                outfile.write('# Pattern Center\n')
                np.savetxt(outfile, self.C.reshape((1,-2)))
                outfile.write('# Pattern Profile {0}\n'.format(data.shape))
                np.savetxt(outfile, np.rot90(data ,k=3))
                if self.plot_sim:
                    if len(self.simulations) >= 3:
                        sim_len_i = 3
                    else:
                        sim_len_i = len(self.simulations)
                    simulation = self.simulations[-sim_len_i]
                    sim = simulation.srdf/simulation.sdrdf**1.5
                    sim_norm = sim/float(max(sim))
                    #print(sim, max(sim[1:]), min(sim[1:]), sim_norm)
                    #simulation.sdrdf, 0, sim_norm*simulation.sim_intens, color[col_index] ,linewidth = 2, zorder = 2)
                    sim = np.array([sim_norm*simulation.sim_intens, simulation.sdrdf])
                    outfile.write('# Pattern Simulation {0}\n'.format(sim.shape))
                    print(sim.shape, sim)
                    np.savetxt(outfile, np.rot90(sim ,k=3))
            # Open the file for write, write, close
#            self.filename=dlg.GetFilename()
#            self.dirname=dlg.GetDirectory()
#            filehandle=open(os.path.join(self.dirname, self.filename),'w')
#            filehandle.write(itcontains)
#            filehandle.close()
            # Get rid of the dialog to keep things tidy
            dlg.Destroy()
        
    def onclick_lable(self,event):
        #global eid
        #global radframe
        
        num_inter = 40
        text_offset = 0.07
        
        axi2 = self.canvas.figure.axes[0]
                
        print('button=%d, x=%d, y=%d, xdata=%f, ydata=%f'%(
            event.button, event.x, event.y, event.xdata, event.ydata))
        ax = event.xdata
        ay = event.ydata
        
        peak_i = self.peak_fit(ax, num_inter = num_inter)
        
        axi2.set_autoscale_on(False)
        axi2.plot(self.t, self.peak_parab)
        
        if peak_i == 0 or peak_i == num_inter-1:
            peak = ax
            text_pos = self.peak_parab[abs(self.t - peak).argmin(0)]+text_offset
        else:
            peak = self.t[peak_i]
            text_pos = self.peak_parab[peak_i]+text_offset
        
        dspace = 1/peak
        print(dspace)
        
        axi2.plot(peak, text_pos-text_offset, 'b+')
        
        dspace_str = '%.2f' % dspace + self.angstrom
        bbox_props = dict(boxstyle="round", fc="c", ec="0.5", alpha=0.5)
        axi2.text(peak, text_pos, dspace_str, ha="center", va="bottom", size=10, rotation=90,
            bbox=bbox_props)
        axi2.figure.canvas.draw()
        #radframe.canvas.mpl_disconnect(eid)
        #print("Press 'm' mark additional peaks.")
    
    def peak_fit(self, ax, poly_degree = 4, fit_range = 2, num_inter = 40):
        
        points = abs(self.drdf - ax)
        i = points.argmin(0)
        
        if self.plot_polar:
            fit_range = 4
        
        #print(self.drdf, ax, self.drdf[i-fit_range:i+fit_range+1])
        
        # form the Vandermonde matrix
        A = np.vander(self.drdf[i-fit_range:i+fit_range+1], poly_degree)
 
        # find the x that minimizes the norm of Ax-y
        (coeffs, residuals, rank, sing_vals) = np.linalg.lstsq(A, self.rdf[i-fit_range:i+fit_range+1])
 
        # create a polynomial using coefficients
        parab = np.poly1d(coeffs)
        
        self.t = np.linspace(self.drdf[i-fit_range],self.drdf[i+fit_range],num_inter)
        
        self.peak_parab = parab(self.t)
        
        return parab(self.t).argmax(0)
        
    def onclick_fitback(self,event):
        
        axi2 = self.canvas.figure.axes[0]
        
        print('button=%d, x=%d, y=%d, xdata=%f, ydata=%f'%(
            event.button, event.x, event.y, event.xdata, event.ydata))
        ax = event.xdata
        
        points = abs(self.drdf - ax)
        i = points.argmin(0)
        
        #self.use_voigt = 1
        
        def power(d,p):
            return(p[0]*d**(-p[1]))
        
        def voigt(x,p):
            """\
            voigt profile

            V(x,sig,gam) = Re(w(z))/(sig*sqrt(2*pi))
            z = (x+i*gam)/(sig*sqrt(2))
             """
            pos = 0
            amp = p[0]
            fwhm = p[1]
            shape = p[2]
            
            tmp = 1/scipy.special.wofz(np.zeros((len(x))) \
                +1j*np.sqrt(np.log(2.0))*shape).real
            tmp = tmp*amp* \
                scipy.special.wofz(2*np.sqrt(np.log(2.0))*(x-pos)/fwhm+1j* \
                np.sqrt(np.log(2.0))*shape).real + p[3]
            return tmp
        
        if self.use_voigt:
            func = voigt
            p0 = [2,0.0002,1000, 0]# initial guesses
            self.back_fit_points = 5
        else:
            func = power
            p0 = [10,1]# initial guesses
            self.back_fit_points = 3
        
            
        if event.xdata != None and event.ydata != None and event.button == 1:
            if not self.bgfitp.size: self.bgfitp = np.array([ax,self.rdf[i]])
            else: self.bgfitp = np.vstack((self.bgfitp, np.array([ax,self.rdf[i]])))
    
            print(self.bgfitp, self.bgfitp.size)
    
            axi2.set_autoscale_on(False)
            point_mark = axi2.plot(ax, self.rdf[i], 'b+')
            #axi.set_ylim(0, size[0])
            axi2.figure.canvas.draw()

        if self.bgfitp.size >= (self.back_fit_points * 2):
            
            self.background_sub = 1
            
            r = self.bgfitp[:,0]
            d = self.bgfitp[:,1]
            
            def residuals(p, r, d):
                err = r - func(d, p)
                return err
           
            guessfit = func(self.drdf,p0)
            #axi2.plot(self.drdf,guessfit,'g')
            
            pbest = leastsq(residuals,p0,args=(d,r),full_output=1)
            
            bestparams = pbest[0]
            cov_x = pbest[1]
            print('best fit parameters ',bestparams)
            print(cov_x)
        
            self.background = func(self.drdf,bestparams)
            
            #if plot_sub:
            #    axi2.lines.pop(-2)
            #    axi2.figure.canvas.draw()
            
            plot_sub = axi2.plot(self.drdf,self.background,'r')
            
            axi2.figure.canvas.draw()
            
            rdf_max = self.rdf.max()
            
            self.rdf -= self.background
            
            #self.background[nonzero(self.background > rdf_max)] = rdf_max
            #plot_sub = axi2.plot(self.drdf,self.background,'m')
            
            start = np.nonzero(self.rdf>0)[0][0]
            
            print(self.rdf[start:].min())
            
            self.rdf -= self.rdf[start:].min()
            
            self.rdf[0:start] = 0
            
            self.rdfb += [self.rdf.copy()]
            self.drdfb += [self.drdf.copy()]
            
            axi2.plot(self.drdf,self.rdf,'k')
            
            axi2.figure.canvas.draw()
            
            self.bgfitp = np.array([])
            print(self.toolbar.fid)
            self.toolbar.fid = self.canvas.mpl_disconnect(self.toolbar.fid)
            print(self.toolbar.fid)

    def OnClearPro(self,e):
        self.axes.cla()
        
        self.plot(2)
        self.axes.figure.canvas.draw()
        
    def OnClearProSim(self,e):
        self.prosim = 0
        self.axes.cla()
        self.plot(2)
        self.axes.figure.canvas.draw()
        
    def OnClearSim(self,e):
    
        self.simulations.pop(-1)
        if len(self.simulations) <= 0:
            self.plot_sim = 0
        
        self.axes.cla()
        
        self.plot(2)
        self.axes.figure.canvas.draw()    
                
            
    def OnUndo(self,e):
        axi2 = self.canvas.figure.axes[0]
        
        axi2.cla()
        print(len(self.rdfb), len(self.rdfb[-1]), len(self.drdfb[-1]))
        if len(self.rdfb) > 1:
            print(self.rdfb[-1])
            self.rdfb.pop(-1)
            self.drdfb.pop(-1)
        print(len(self.rdfb), len(self.rdfb[-1]), len(self.drdfb[-1]) , self.rdfb[-1])
        self.rdf = self.rdfb[-1].copy()
        self.drdf = self.drdfb[-1].copy()
            
        self.plot(2)
        axi2.figure.canvas.draw()
        
    def OnPolar(self,e):
        self.axes.cla()
        #plot_polar_pattern(self.pattern_open, self.C, self.boxs, self.rdf, self.drdf)
        origin =  [self.C[1], self.C[0]]
    
        polar_grid, r, theta, pmrdf, self.psrdf, self.prrdf = reproject_image_into_polar(self.pattern_open, origin, self.boxs)
        self.plot_polar = 1
        
        self.polar_grid = polar_grid

        rdf = np.array(self.rdf)
        drdf = np.array(self.drdf)
        #print(pmrdf.shape, psrdf.max())
        self.dpmrdf = np.arange(pmrdf.shape[0])*(self.pixel_size / 10**10)
        #print(dpmrdf.shape)
    
        #rdf /= rdf.max()
        #pmrdf /= pmrdf.max()
        #self.psrdf /= self.psrdf.max()
        
        self.rdf = rdf
        self.drdf = drdf
        
        self.rdfb += [self.rdf.copy()]
        self.drdfb += [self.drdf.copy()]
        
        self.plot(2,'b')        
        
        self.rdf = pmrdf
        self.drdf = self.dpmrdf
        
        self.rdf_max = self.rdf.max()
        
        self.rdfb += [self.rdf.copy()]
        self.drdfb += [self.drdf.copy()]
        
        self.plot(2,'r')
        
        #self.rdf = self.psrdf
        #self.drdf = dpmrdf
        
        #self.rdfb += [self.rdf.copy()]
        #self.drdfb += [self.drdf.copy()]        
        
        #self.plot(2,'g')        
        
        self.axes.figure.canvas.draw()
    def OnBeamStop(self,e):
        #if not self.plot_polar:
        self.OnPolar(e)
        self.rdf = self.psrdf
        self.drdf = self.dpmrdf
        
        self.rdf_max = self.rdf.max()
        
        self.rdfb += [self.rdf.copy()]
        self.drdfb += [self.drdf.copy()]        
        
        self.plot(2,'g')
        
        self.axes.figure.canvas.draw()
                
                
    def OnRemoveSpots(self,e):
        #if not self.plot_polar:
        self.OnPolar(e)
        self.rdf = self.prrdf
        self.drdf = self.dpmrdf
        
        self.rdf_max = self.rdf.max()
        
        self.rdfb += [self.rdf.copy()]
        self.drdfb += [self.drdf.copy()]        
        
        self.plot(2,'k')
        
        self.axes.figure.canvas.draw()
                
    def OnSimOpen(self,e):
        # In this case, the dialog is created within the method because
        # the directory name, etc, may be changed during the running of the
        # application. In theory, you could create one earlier, store it in
        # your frame object and change it when it was called to reflect
        # current parameters / values
        
        cctbx_python_path = None
            
        # Look for cctbx.python
        home = os.path.expanduser('~')
        #print(os.listdir(home))
        for f_name in os.listdir(home):
            if f_name.startswith('cctbx'):
                cctbx_python_path = os.path.join(home,f_name,'build','bin','cctbx.python')
        
        if cctbx_python_path == None:
            error_cctbx = 'Could not find cctbx.\nPlease download cctbx: http://cci.lbl.gov/cctbx_build/ \nand extract it to: ' + str(home)
            print(error_cctbx)
            error_int_dlg = Error(self, -1, 'Error', error_cctbx)
            error_int_dlg.Show(True)
            error_int_dlg.Centre()
        else:
            dlg = wx.FileDialog(self, "Choose a CIF crystal file",
                self.dirname, "", "CIF|*.cif;*.CIF|All Files|*.*", wx.FD_OPEN)
            if dlg.ShowModal() == wx.ID_OK:
                            
                filename=dlg.GetFilename()
                self.dirname=dlg.GetDirectory()
                
                print(self.dirname)
                
                #print(count, centers, circle)
                
                name, ext = os.path.splitext(filename)
                
                di_max = self.limit
                d_min = str(1/di_max)

                cif_name = os.path.join(self.dirname, filename)
                
                def voigt(x,amp,pos,fwhm,shape):
                     """\
                    voigt profile

                    V(x,sig,gam) = Re(w(z))/(sig*sqrt(2*pi))
                    z = (x+i*gam)/(sig*sqrt(2))
                     """

                     tmp = 1/special.wofz(np.zeros((len(x))) \
                           +1j*np.sqrt(np.log(2.0))*shape).real
                     tmp = tmp*amp* \
                           special.wofz(2*np.sqrt(np.log(2.0))*(x-pos)/fwhm+1j* \
                           np.sqrt(np.log(2.0))*shape).real
                     return tmp

                cctbx_script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'iotbx_cif.py'))

                print(cctbx_python_path, cctbx_script_path)
                
                shell_args = [cctbx_python_path, cctbx_script_path, cif_name, d_min, 'sf']
                pro_args = dict(args = shell_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if os.name == 'nt':
                    pro_args['shell'] = True
                    
                shell_args[-1] = 'sf'
                sf_output, sf_error = subprocess.Popen(**pro_args).communicate()
                print(sf_output)
                
                shell_args[-1] = 'ds'
                ds_output, sf_error = subprocess.Popen(**pro_args).communicate()
                print(ds_output)
                
                shell_args[-1] = 'mt'
                mt_output, sf_error = subprocess.Popen(**pro_args).communicate()
                print(mt_output)

                sf_data = np.genfromtxt(BytesIO(sf_output), dtype=None, names=('h','k','l','sf'))

                #print sf_data.shape
                sf= sf_data['sf']
                print(sf)

                ds_data = np.genfromtxt(BytesIO(ds_output), dtype=None, names=('h','k','l','ds'))

                #print ds_data.shape
                ds= ds_data['ds']
                print(ds)

                mt_data = np.genfromtxt(BytesIO(mt_output), dtype=None, names=('h','k','l','mt'))

                #print ds_data.shape
                mt= mt_data['mt']
                print(mt)


                hkl_list = []
                for h,k,l in zip(ds_data['h'],ds_data['k'],ds_data['l']):
                    hkl_list += [''.join([str(h.translate(None,b' (),'),"utf-8"), str(k.translate(None,b' (),'),"utf-8"), str(l.translate(None,b' (),'),"utf-8")])]
                    
                print(hkl_list)

                # Mott–Bethe formula to correct for electrons
                #meh = 0.026629795
                sfc2 = (sf)/((1/ds)**(2.5))

                intense = sfc2*mt

                intensen = intense/intense.max()

                ## Broden
                x = np.linspace(0,di_max,1000)
                di =1/ds
                vois =[]
                for i,d in zip(intensen,di):
                    vois += [voigt(x,i,d,0.02,1)]

                brd = np.array(vois).sum(axis=0)

                dtypes = [('inv_d',float),('intensity',float),('index','<U4')]
                sim_open = np.array(list(zip(di,intensen,hkl_list)), dtypes)
                sim_open.sort(order='inv_d')
                print(sim_open,sim_open.shape,len(sim_open.shape))
                self.simulations += [sim_i.Simulation(name, sim_open[['inv_d','intensity']], sim_open['index'])]
                
                self.plot_sim = 1
                self.prosim = 1
                self.prosim_int = brd
                self.prosim_inv_d = x
                
                self.axes.cla()
                self.plot(2,'b')        
                
                self.axes.figure.canvas.draw()
                
                dlg.Destroy()
    
    def OnSim2Open(self,e):
        # In this case, the dialog is created within the method because
        # the directory name, etc, may be changed during the running of the
        # application. In theory, you could create one earlier, store it in
        # your frame object and change it when it was called to reflect
        # current parameters / values
        dlg = wx.FileDialog(self, "Choose a GDIS electron powder plot with a wavelength of .5 and with U,V,W set to 0",
            self.dirname, "", "txt|*.txt;*.TXT|All Files|*.*", wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
                        
            filename=dlg.GetFilename()
            self.dirname=dlg.GetDirectory()
            name, ext = os.path.splitext(filename)
            print(self.dirname)
            
            try:
                sim_open = np.loadtxt(os.path.join(self.dirname, filename),skiprows=0)
            except:
                dlg.Destroy()
                error_file = 'File must be an exported GDIS Graph.'
                print(error_file)
                error_int_dlg = Error(self, -1, 'Error', error_file)
                error_int_dlg.Show(True)
                error_int_dlg.Centre()
            else:
                print(len(np.nonzero(sim_open[:,1])[0]))
                if len(np.nonzero(sim_open[:,1])[0]) <= 200:
                    self.simulations += [sim_i.Simulation(name, sim_open)]
                    
                    self.plot_sim = 1
                    
                    self.axes.cla()
                    self.plot(2,'b')        
                    
                    self.axes.figure.canvas.draw()
                    
                    dlg.Destroy()
                else:
                    dlg.Destroy()
                    error_file = 'File must have less than 200 peaks.'
                    print(error_file)
                    error_int_dlg = Error(self, -1, 'Error', error_file)
                    error_int_dlg.Show(True)
                    error_int_dlg.Centre()
    
    def OnProSimOpen(self,e):
        # In this case, the dialog is created within the method because
        # the directory name, etc, may be changed during the running of the
        # application. In theory, you could create one earlier, store it in
        # your frame object and change it when it was called to reflect
        # current parameters / values
        dlg = wx.FileDialog(self, "Choose a GDIS electron powder plot with a wavelength of .5, with Lorentzian, and with U,V,W set to 0.6",
            self.dirname, "", "txt|*.txt;*.TXT|All Files|*.*", wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
                        
            filename=dlg.GetFilename()
            self.dirname=dlg.GetDirectory()
            name, ext = os.path.splitext(filename)
            print(self.dirname)
            
            try:
                sim_open = np.loadtxt(os.path.join(self.dirname, filename),skiprows=0)
            except:
                dlg.Destroy()
                error_file = 'File must be an exported GDIS Graph.'
                print(error_file)
                error_int_dlg = Error(self, -1, 'Error', error_file)
                error_int_dlg.Show(True)
                error_int_dlg.Centre()
            else:
                self.prosim = 1
                theta_2 = sim_open[:,0]
                inv_d = (2*np.sin(((theta_2/180)*np.pi)/2.))/.5
                
                intensity = sim_open[:,1]
                intensity /= intensity.max()

                print(sim_open.shape, len(theta_2), len(intensity))

                #self.axes.plot(inv_d,intensity)
                #self.axes.figure.canvas.draw()
                
                self.prosim_int = intensity
                self.prosim_inv_d = inv_d
                self.prosim_theta_2 = theta_2
                
                self.axes.cla()
                self.plot(2,'b')
                self.axes.figure.canvas.draw()
                
                dlg.Destroy()

    def OnRingPattern(self,e):
        ringframe = ring_pattern.ring_pattern(self)
        ringframe.Show(True)
            
    def OnSimLabel(self,e):
        dlg = sim_i.Index(self, -1, 'Index Peaks')
        dlg.Show(True)
        
    def OnPro_Pref(self,e):
        dlg = Pro_Pref(self, -1, 'Profile Preferences')
        dlg.Show(True)
        dlg.Centre()

class Pro_Pref(wx.Dialog):
    def __init__(self, parent, id, title):
    
        wx.Dialog.__init__(self, parent, id, title, wx.DefaultPosition, wx.Size(400, 400))
        
        self.parent = parent
        
        wx.StaticText(self, -1, u'Scattering Vector Limit (1/\u00c5): ', (20, 20))
        #wx.StaticText(self, -1, 'Latex Text Rendering: ', (20, 70))
        #wx.StaticText(self, -1, 'Show Polar Pattern: ', (20, 120))
        #wx.StaticText(self, -1, 'Polar Pattern Negative: ', (20, 170))    
        wx.StaticText(self, -1, 'Polar Pattern Gamma: ', (20, 270))
        
        limit_string =     '%.2f' % self.parent.limit    
        self.limit_tc = wx.TextCtrl(self, -1, '',  (250, 15), (60, -1))
        self.limit_tc.SetValue(limit_string)        
        
        self.voigt_cb = wx.CheckBox(self, -1, 'Voigt for Background Sub (5 points)', (20, 65))
        self.voigt_cb.SetValue(self.parent.use_voigt)

        self.latex_cb = wx.CheckBox(self, -1, 'Latex Text Rendering', (20, 115))
        self.latex_cb.SetValue(self.parent.latex)
        
        self.polar_cb = wx.CheckBox(self, -1, 'Show Polar Pattern', (20, 165))
        self.polar_cb.SetValue(self.parent.show_polar)
        
        self.polar_neg_cb = wx.CheckBox(self, -1, 'Polar Pattern Negative', (20, 215))
        self.polar_neg_cb.SetValue(self.parent.polar_neg)
        
        self.gamma_tc = wx.TextCtrl(self, -1, '',  (250, 265), (60, -1))
        self.gamma_tc.SetValue(str(self.parent.gamma))                    
        
        set_btn = wx.Button(self, 1, 'Set', (70, 325))
        set_btn.SetFocus()
        close_btn = wx.Button(self, 2, 'Close', (185, 325))

        self.Bind(wx.EVT_BUTTON, self.OnSet, id=1)
        self.Bind(wx.EVT_BUTTON, self.OnClose, id=2)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        
    def OnSet(self, event):
        
        self.parent.limit = float(self.limit_tc.GetValue())
        self.parent.use_voigt = self.voigt_cb.GetValue()
        self.parent.latex = self.latex_cb.GetValue()
        self.parent.show_polar = self.polar_cb.GetValue()
        self.parent.polar_neg = self.polar_neg_cb.GetValue()
        self.parent.gamma = float(self.gamma_tc.GetValue())
        
        #print(self.parent.polar_neg)
        
        self.parent.axes.cla()
        self.parent.plot(2)            
        self.parent.axes.cla()
        self.parent.plot(2)
        self.parent.axes.figure.canvas.draw()
        self.Destroy()
        
    def OnClose(self, event):
        self.Destroy()

