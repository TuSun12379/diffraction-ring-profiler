#!/usr/bin/env python
"""
Makes ring patterns from profiles
"""
from numpy import *

import matplotlib

from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg

from matplotlib.backends.backend_wx import _load_bitmap
from matplotlib.figure import Figure
from numpy.random import rand

import wx
import os

from numpy import *
import scipy.constants as con
from scipy.optimize import leastsq
#import scipy.linalg
from matplotlib.pyplot import *
import matplotlib.patches as patches

from polar_pattern import *
from sim_index import *

import ring_pattern

import time

class Timer():
   def __enter__(self): self.start = time.time()
   def __exit__(self, *args): print time.time() - self.start

from matplotlib import rc

rc('savefig', dpi=600)

class MyNavigationToolbar2(NavigationToolbar2WxAgg):
    """
    Extend the default wx toolbar with your own event handlers
    """
    def __init__(self, parent, canvas, cankill):
        NavigationToolbar2WxAgg.__init__(self, canvas)
        
        self.parent = parent
        
    def mouse_move(self, event):
        #print 'mouse_move', event.button
                
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
        cursor =wx.StockCursor(cursord[cursor])
        self.canvas.SetCursor( cursor )

class ring_pattern(wx.Frame):

    def __init__(self, parent):
        wx.Frame.__init__(self,parent,-1,"Ring Figure - "+parent.filename ,size=(550,350))
                
        iconFile = "icons/diff_profiler_ico.ico"
        icon1 = wx.Icon(iconFile, wx.BITMAP_TYPE_ICO)
        
        self.SetIcon(icon1)
        
        self.parent = parent
            
        # dirname is an APPLICATION variable that we're choosing to store
        # in with the frame - it's the parent directory for any file we
        # choose to edit in this frame
        self.dirname = ''

        self.statbar = self.CreateStatusBar() # A Statusbar in the bottom of the window
        self.statbar.SetFieldsCount(2)
        self.statbar.SetStatusText("None", 1)
        
        self.SetBackgroundColour(wx.NamedColor("WHITE"))

        self.figure = Figure(figsize=(6,6), dpi=76)
        self.axes = self.figure.add_axes([0,0,1,1],yticks=[],xticks=[],frame_on=False)#
        
        self.canvas = FigureCanvas(self, -1, self.figure)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.canvas, 1, wx.TOP | wx.LEFT | wx.EXPAND)
        # Capture the paint message
        wx.EVT_PAINT(self, self.OnPaint)
        
        self.toolbar = MyNavigationToolbar2(self, self.canvas, True)
        self.toolbar.Realize()
        if wx.Platform == '__WXMAC__':
            # Mac platform (OSX 10.3, MacPython) does not seem to cope with
            # having a toolbar in a sizer. This work-around gets the buttons
            # back, but at the expense of having the toolbar at the top
            self.SetToolBar(self.toolbar)
        else:
            # On Windows platform, default window size is incorrect, so set
            # toolbar width to figure width.
            tw, th = self.toolbar.GetSizeTuple()
            fw, fh = self.canvas.GetSizeTuple()
            # By adding toolbar in sizer, we are able to put it at the bottom
            # of the frame - so appearance is closer to GTK version.
            # As noted above, doesn't work for Mac.
            self.toolbar.SetSize(wx.Size(fw, th))
            self.sizer.Add(self.toolbar, 0, wx.LEFT | wx.EXPAND)
        # update the axes menu on the toolbar
        self.toolbar.update()        

        self.SetSizer(self.sizer)
        self.Fit()
        
        self.ring_plot()


        
    def OnPaint(self, event):
        self.canvas.draw()
        event.Skip()
        
    def ring_plot(self):
        
        #rc('font', size=16)
        
        if self.parent.latex:
            rc('text', usetex=True)
            rc('font', family='serif')
        else:
            rc('text', usetex=False)
            rc('font', family='sans-serif')
            rc('mathtext', fontset = 'custom')
        
        origin =  [round(self.parent.C[1]), round(self.parent.C[0])]
        
        #pattern_open_crop = self.parent.pattern_open[origin[0]-(self.parent.boxs-6):origin[0]+(self.parent.boxs-3),origin[1]-(self.parent.boxs-6):origin[1]+(self.parent.boxs-3)]
        pattern_open_crop = self.parent.pattern_open[origin[0]-(self.parent.boxs):origin[0]+(self.parent.boxs),origin[1]-(self.parent.boxs):origin[1]+(self.parent.boxs)]
        
        if self.parent.background_sub == 1:
            back_patt = make_profile_rings(self.parent.background - self.parent.background.min(), self.parent.drdf, origin, self.parent.boxs, True)
            #figure()
            #imshow(back_patt, cmap = 'gray')
            #show()
            print pattern_open_crop.shape, back_patt.shape, origin
            print self.parent.rdf.max(), back_patt.max(), pattern_open_crop.max(), self.parent.rdf_max
            
            middle_x = back_patt.shape[1]/2
            
            back_patt = back_patt * self.parent.rdf_max
            #figure()
            #plot(back_patt[:,middle_x])
            #plot(pattern_open_crop[:,middle_x])
            #line = pattern_open_crop[:,middle_x] - back_patt[:,middle_x]
            #plot(line)
            #line[line < 0] = 0
            #plot(line)
            
            pattern_open_crop = pattern_open_crop.astype(float32)

            pattern_open_crop -= back_patt
            #plot(pattern_open_crop[:,middle_x])
            pattern_open_crop[pattern_open_crop < 0] = 0
            #plot(pattern_open_crop[:,middle_x])
            #show()
            print pattern_open_crop.min(), pattern_open_crop.max()

        self.axes.imshow(pattern_open_crop, cmap = 'gray',
                extent=(-self.parent.drdf.max(), self.parent.drdf.max(), -self.parent.drdf.max(), self.parent.drdf.max()))
        
        if self.parent.prosim == 1:
            
            ring_patt = make_profile_rings(self.parent.prosim_int, self.parent.prosim_theta_2, origin, self.parent.boxs)
            self.axes.imshow(ring_patt[:,:ring_patt.shape[1]/2], cmap='gray', origin='lower',
                extent=(-self.parent.prosim_inv_d.max(), 0, -self.parent.prosim_inv_d.max(), self.parent.prosim_inv_d.max()))
            print self.parent.prosim_inv_d.max()
        if self.parent.plot_sim == 1:
            sim_name = []
            marks = []
            color = ['#42D151','#2AA298','#E7E73C']
            marker = ['o','^','s']
            print len(self.parent.simulations)#, self.srdfb
            if len(self.parent.simulations) >= 3:
                sim_len_i = 3
            else:
                sim_len_i = len(self.parent.simulations)
            print sim_len_i#,self.srdfb[sim_len_i[0]],self.sdrdfb[sim_len_i[0]]
            for col_index, simulation in enumerate(self.parent.simulations[-sim_len_i:]):
                sim_color = simulation.sim_color if simulation.sim_color else color[col_index]
                sim_name += [simulation.sim_label]
                sim = simulation.srdf
                sim_norm = sim/float(max(sim))
                #print sim, max(sim[1:]), min(sim[1:]), sim_norm
                marks += [self.axes.plot(0,0,'-',color=sim_color, zorder = -10)]
                rect = Rectangle((-self.parent.limit,-self.parent.limit),self.parent.limit,self.parent.limit, facecolor="none", edgecolor="none")
                self.axes.add_patch(rect)
                if not simulation.peak_index_labels:
                    for radius in simulation.sdrdf:
                        #print radius
                        circ_mark = patches.Circle((0,0), radius, fill = 0 , color=sim_color, linewidth = 2, alpha=.7)
                        self.axes.add_patch(circ_mark)
                        circ_mark.set_clip_path(rect)
                        self.axes.set_autoscale_on(False)
                    #sim_index = nonzero(self.srdfb[i]!=0)
                else:
                    j=0
                    for i,label in enumerate(simulation.peak_index_labels[::-1]):
                        #print label
                        if label:
                            circ_mark = patches.Circle((0,0), simulation.sdrdf[::-1][i], fill = 0 , color=sim_color, linewidth = 2, alpha=.7)
                            self.axes.add_patch(circ_mark)
                            circ_mark.set_clip_path(rect)
                            self.axes.set_autoscale_on(False)
                            
                            if label.find('-') == -1:
                                label = r'('+label+')'
                            else:
                                label = r'$\mathsf{('+label.replace('-',r'\bar ')+')}$'
                            #print label
                            bbox_props = dict(boxstyle="round", fc=sim_color, ec="0.5", alpha=1, lw=1.5)
                            arrowprops=dict(arrowstyle="wedge,tail_width=1.",
                                fc=sim_color, ec="0.5",
                                alpha=.7,
                                patchA=None,
                                patchB=circ_mark,
                                relpos=(0.5, 0.5),
                                )
                            an = self.axes.annotate(label, xy=(0, 0),xytext=(.1+col_index/10.0, .1+j/15.0),textcoords='axes fraction', ha="center", va="center", size=16, rotation=0, zorder = 90-col_index, picker=True,
                                bbox=bbox_props, arrowprops=arrowprops)
                            an.draggable()
                            j+=1


            
            print sim_name, marks 
            leg = self.axes.legend(marks , sim_name, loc='upper left', shadow=0, fancybox=True, numpoints=1, prop={'size':16})    
            frame = leg.get_frame()
            frame.set_alpha(0.7)
            for handle in leg.legendHandles:
                handle.set_linewidth(3.0)

        #self.axes.plot(0,0,'+')
        #self.axes.axis('equal')
        self.axes.set_xlim(-self.parent.limit, self.parent.limit)
        self.axes.set_ylim(-self.parent.limit, self.parent.limit)
        #self.axes.xaxis.set_ticks_position('bottom')
        #self.axes.yaxis.set_ticks_position('left')
        
        
        self.axes.figure.canvas.draw()


