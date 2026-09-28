import ghidra.app.script.GhidraScript;
import ghidra.program.model.mem.*;
public class SetExec extends GhidraScript {
    public void run() throws Exception {
        for (MemoryBlock b : currentProgram.getMemory().getBlocks())
            if (b.getName().startsWith("RAM_P") || b.getName().equals("ram")) b.setExecute(true);
    }
}
