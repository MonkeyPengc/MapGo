
## -----------------------------------------------------------------------------
# define a function that generates location points
def parse_file(blob_reader):
    locations = []
    for line in blob_reader:
        if not line:
            continue
        gps = line.replace(',',' ').split()
        locations.append("|" + '{0}, {1}'.format(gps[0], gps[1]))
    return locations


# -----------------------------------------------------------------------------
# define a function that generates URL of the queried map
def generate_url(center=None, zoom=18, imgsize="640x640", maptype="satellite", locations=None, markers=None):
    """       
        An example of URL:
        https://maps.googleapis.com/maps/api/staticmap?center=Brooklyn+Bridge,New+York,NY&zoom=13
        &size=600x300&maptype=roadmap&markers=color:blue%7Clabel:S%7C40.702147,-74.015794
        &markers=color:green%7Clabel:G%7C40.711614,-74.012318
        &path=color:0x0000ff|weight:5|40.737102,-73.990318|40.749825,-73.987963
    """
    url = "http://maps.google.com/maps/api/staticmap?"  # base URL

    # if center and zoom  are not given, the map will show all marker locations
    if center != None:
        url += "center=%s&" % center
    url += "zoom=%i&" % zoom
    url += "size=%s&" % imgsize  
    url += "maptype=%s&" % maptype
    
    if locations != None:
        url += "&path=color:0x0000ff|weight:5"
        for location in locations:
            url += "%s" % location

    # add markers (lat and lon)
    if markers != None:
        for marker in markers:
            url += "%s&" % marker
    url += "&sensor=true"
    return url


