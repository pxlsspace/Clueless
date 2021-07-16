


def format_table(table,column_names,alignments=None,name=None):
    ''' Format the leaderboard in a string to be printed
    - :param table: a 2D array to format
    - :param column_names: a list of column names, must be the same lengh as the table rows
    - :alignments: a list of alignments
        - '^': centered
        - '<': aligned on the left
        - '>': aligned on the right
    - :name: add a '+' in front of of the row containing 'name' in the 2nd column'''
    if not table:
        return
    if len(table[0]) != len(column_names):
        raise ValueError("The number of column in table and column_names don't match.")
    if alignments and len(table[0]) != len(alignments):
        raise ValueError("The number of column in table and alignments don't match.")

    # find the longest columns
    table.insert(0,column_names)
    longest_cols = [
        (max([len(str(row[i])) for row in table]))
        for i in range(len(table[0]))]

    # format the header
    LINE = "-"*(sum(longest_cols) + len(table[0]*3))
    if alignments:
        row_format = " | ".join([f"{{:{alignments[i]}" + str(longest_col) + "}" for i,longest_col in enumerate(longest_cols)])
        title_format = row_format
    else:
        title_format = " | ".join(["{:^" + str(longest_col) + "}" for longest_col in longest_cols])

        row_format = " | ".join(["{:>" + str(longest_col) + "}" for longest_col in longest_cols])


    str_table = f'{LINE}\n'
    str_table += "  " if name else " " 
    str_table += f'{title_format.format(*table[0])}\n{LINE}\n'

    # format the body
    for row in table[1:]:
        if name:
            str_table += ("+ " if row[1] == name else "  ") + row_format.format(*row) + "\n"
        else:
            str_table += " " + row_format.format(*row) + "\n"

    return str_table

def format_number(num):
    ''' format a number in a string: 1234567 -> 1 234 567'''
    return f'{int(num):,}'.replace(","," ") # convert to string