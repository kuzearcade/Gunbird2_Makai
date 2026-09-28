// Pre-script for DC 1ST_READ.BIN (SH-4 LE, base 0x8C010000): entry function + aggressive finder
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
public class SetupDC extends GhidraScript {
    public void run() throws Exception {
        setAnalysisOption(currentProgram, "Aggressive Instruction Finder", "true");
        AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
        createFunction(sp.getAddress(0x8C010000L), "entry");
        currentProgram.getMemory().getBlocks()[0].setWrite(true);
        currentProgram.getMemory().getBlocks()[0].setExecute(true);
    }
}
